# Versão: v90 (Otimização: Limite de 500 no Dashboard + Correção Spinner com Cookie)
import os
import io
import zipfile
import csv
import json
import shutil
import pandas as pd
import xml.etree.ElementTree as ET
from xml.dom import minidom
# v90: make_response foi adicionado para cookies
from flask import Flask, render_template, request, redirect, url_for, flash, get_flashed_messages, session, make_response, send_file
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import sessionmaker, relationship, declarative_base, joinedload, selectinload
from sqlalchemy.pool import StaticPool
from googletrans import Translator

# --- Configuração ---
basedir = os.path.abspath(os.path.dirname(__file__))
DATABASE_FOLDER = os.path.join(basedir, 'databases')
if not os.path.exists(DATABASE_FOLDER):
    os.makedirs(DATABASE_FOLDER)

TEMPLATE_DB_NAME = 'Neat7_template_v68.db'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma-chave-secreta-muito-forte-v90' 
translator = Translator()

# --- Definição dos Modelos (v68+) ---
Base = declarative_base()

class Areas(Base):
    __tablename__ = 'areas'
    area_id = Column(Integer, primary_key=True)
    nome_area = Column(String, nullable=False, unique=True)
    descricao = Column(String)
    unidades = relationship('Unidades', back_populates='area', cascade="all, delete-orphan", lazy='joined')

class Unidades(Base):
    __tablename__ = 'unidades'
    unidade_id = Column(Integer, primary_key=True)
    nome_unidade = Column(String, nullable=False, unique=True)
    descricao = Column(String)
    area_id = Column(Integer, ForeignKey('areas.area_id'), nullable=False)
    area = relationship('Areas', back_populates='unidades', lazy='joined')
    phases = relationship('Phases', back_populates='unidade', cascade="all, delete-orphan", lazy='dynamic')

class Phases(Base):
    __tablename__ = 'phases'
    phase_id = Column(Integer, primary_key=True)
    nome_phase = Column(String, nullable=False)
    tipo_phase = Column(String, nullable=False)
    descricao_pt = Column(String)
    descricao_en = Column(String)
    descricao_es = Column(String)
    unidade_id = Column(Integer, ForeignKey('unidades.unidade_id'), nullable=False)
    unidade = relationship('Unidades', back_populates='phases', lazy='joined')
    parametros = relationship('Parametros', backref='phase', lazy='joined', cascade="all, delete-orphan")
    passos = relationship('Passos', backref='phase', lazy='joined', cascade="all, delete-orphan")
    transition_conditions = relationship('TransitionConditions', backref='phase', lazy='joined', cascade="all, delete-orphan")
    transition_row_descriptions = relationship('TransitionRowDescriptions', backref='phase', lazy='joined', cascade="all, delete-orphan")
    interlocks = relationship('Interlocks', backref='phase', lazy='joined', cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint('unidade_id', 'nome_phase'),)

class Parametros(Base):
    __tablename__ = 'parametros'
    param_id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey('phases.phase_id'), nullable=False)
    numero_param = Column(Integer, nullable=False)
    nome_param = Column(String, nullable=False)
    classe_param = Column(String, nullable=False)
    tipo_dado = Column(String, nullable=False)
    descricao_pt = Column(String)
    descricao_en = Column(String)
    descricao_es = Column(String)
    valor_default = Column(String)
    valor_min = Column(String)
    valor_max = Column(String)
    unidade_engenharia = Column(String)
    __table_args__ = (UniqueConstraint('phase_id', 'classe_param', 'numero_param'), CheckConstraint("tipo_dado IN ('real', 'inteiro', 'bool')"), CheckConstraint("classe_param IN ('PA', 'PE', 'PR')"))

class Passos(Base):
    __tablename__ = 'passos'
    passo_id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey('phases.phase_id'), nullable=False)
    numero_passo = Column(Integer, nullable=False)
    codigo_passo = Column(String)
    descricao_pt = Column(String)
    descricao_en = Column(String)
    descricao_es = Column(String)
    __table_args__ = (UniqueConstraint('phase_id', 'numero_passo'),)

class TransitionConditions(Base):
    __tablename__ = 'TransitionConditions'
    condition_id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey('phases.phase_id'), nullable=False)
    step_index = Column(Integer, nullable=False)
    condition_row = Column(Integer, nullable=False)
    condition_logic = Column(String)
    condition_text_pt = Column(String)
    condition_text_en = Column(String)
    condition_text_es = Column(String)
    __table_args__ = (UniqueConstraint('phase_id', 'step_index', 'condition_row'),)

class TransitionRowDescriptions(Base):
    __tablename__ = 'TransitionRowDescriptions'
    row_desc_id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey('phases.phase_id'), nullable=False)
    row_number = Column(Integer, nullable=False)
    descricao_pt = Column(String)
    descricao_en = Column(String)
    descricao_es = Column(String)
    __table_args__ = (UniqueConstraint('phase_id', 'row_number'),)

class Interlocks(Base):
    __tablename__ = 'interlocks'
    interlock_id = Column(Integer, primary_key=True)
    phase_id = Column(Integer, ForeignKey('phases.phase_id'), nullable=False)
    numero_interlock = Column(Integer, nullable=False)
    seguranca_pt = Column(String)
    seguranca_en = Column(String)
    seguranca_es = Column(String)
    processo_pt = Column(String)
    processo_en = Column(String)
    processo_es = Column(String)
    __table_args__ = (UniqueConstraint('phase_id', 'numero_interlock'),)

engines = {}
def get_db_session(project_name):
    db_path = os.path.join(DATABASE_FOLDER, project_name)
    if not os.path.exists(db_path): raise FileNotFoundError(f"Base de dados {project_name} não encontrada.")
    if project_name not in engines:
        engine = create_engine(f'sqlite:///{db_path}', poolclass=StaticPool, connect_args={'check_same_thread': False})
        Base.metadata.create_all(engine)
        engines[project_name] = engine
    return sessionmaker(bind=engines[project_name])()

def auto_translate(text_pt):
    if not text_pt: return "", ""
    try: return Translator().translate(text_pt, src='pt', dest='en').text, Translator().translate(text_pt, src='pt', dest='es').text
    except: return text_pt, text_pt

def add_xml_text_node(parent, tag, text):
    if text: ET.SubElement(parent, tag).text = text

def generate_steps_xml(phase):
    root = ET.Element('Translations')
    passos_dict = {p.numero_passo: p for p in phase.passos}
    for locale_id, lang_key, prefix in [("1033", "en", "zzEnStep"), ("1046", "pt", "zzStep"), ("3082", "es", "zzEsStep")]:
        steps_node = ET.SubElement(ET.SubElement(root, 'Translation', LocaleID=locale_id), 'Steps')
        for idx_xml in range(50):
            passo_obj = passos_dict.get(idx_xml)
            num, desc = f"zzNumber{idx_xml:03d}", f"{prefix}{idx_xml:03d}"
            if passo_obj:
                num = passo_obj.codigo_passo or num
                if lang_key == "pt": desc = passo_obj.descricao_pt or desc
                elif lang_key == "en": desc = passo_obj.descricao_en or passo_obj.descricao_pt or desc
                elif lang_key == "es": desc = passo_obj.descricao_es or passo_obj.descricao_pt or desc
            step_node = ET.SubElement(steps_node, 'Step')
            add_xml_text_node(step_node, 'Number', num); add_xml_text_node(step_node, 'Description', desc)
    return minidom.parseString(ET.tostring(root, 'utf-8')).toprettyxml(indent="  ", encoding="UTF-8")

def parse_logic_from_text(text):
    if not text or pd.isna(text): return None, "N/A"
    text = str(text).strip()
    if text.endswith(" AND"): return text[:-4].strip(), "AND"
    if text.endswith(" OR"): return text[:-3].strip(), "OR"
    return text, "N/A"

# --- FUNÇÕES EXPORTAÇÃO MASTER (v80) ---
def export_master_areas(dbsession):
    data = [[a.nome_area, a.descricao] for a in dbsession.query(Areas).order_by(Areas.nome_area).all()]
    return pd.DataFrame(data, columns=['Nome_Area', 'Descricao_Area'])
def export_master_unidades(dbsession):
    data = [[u.area.nome_area, u.nome_unidade, u.descricao] for u in dbsession.query(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade).options(joinedload(Unidades.area)).all()]
    return pd.DataFrame(data, columns=['Area', 'Nome_Unidade', 'Descricao_Unidade'])
def export_master_phases(dbsession):
    data = [[p.unidade.area.nome_area, p.unidade.nome_unidade, p.nome_phase, p.tipo_phase, p.descricao_pt, p.descricao_en, p.descricao_es] for p in dbsession.query(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase).options(joinedload(Phases.unidade).joinedload(Unidades.area)).all()]
    return pd.DataFrame(data, columns=['Area', 'Unidade', 'Phase', 'Tipo', 'Desc_PT', 'Desc_EN', 'Desc_ES'])
def export_master_params(dbsession):
    data = []
    for p_obj in dbsession.query(Parametros).join(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase, Parametros.classe_param, Parametros.numero_param).options(joinedload(Parametros.phase).joinedload(Phases.unidade).joinedload(Unidades.area)).all():
        data.append([p_obj.phase.unidade.area.nome_area, p_obj.phase.unidade.nome_unidade, p_obj.phase.nome_phase, p_obj.classe_param, p_obj.numero_param, p_obj.tipo_dado, p_obj.descricao_pt, p_obj.descricao_en, p_obj.descricao_es, p_obj.valor_default, p_obj.valor_min, p_obj.valor_max, p_obj.unidade_engenharia])
    return pd.DataFrame(data, columns=['Area', 'Unidade', 'Phase', 'Classe', 'Numero', 'Tipo', 'Desc_PT', 'Desc_EN', 'Desc_ES', 'Default', 'Min', 'Max', 'Unidade_Eng'])
def export_master_steps(dbsession):
    data = []
    for s_obj in dbsession.query(Passos).join(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase, Passos.numero_passo).options(joinedload(Passos.phase).joinedload(Phases.unidade).joinedload(Unidades.area)).all():
        data.append([s_obj.phase.unidade.area.nome_area, s_obj.phase.unidade.nome_unidade, s_obj.phase.nome_phase, s_obj.numero_passo, s_obj.codigo_passo, s_obj.descricao_pt, s_obj.descricao_en, s_obj.descricao_es])
    return pd.DataFrame(data, columns=['Area', 'Unidade', 'Phase', 'Index', 'Step_Number', 'Desc_PT', 'Desc_EN', 'Desc_ES'])
def export_master_interlocks(dbsession):
    data = []
    for ph_obj in dbsession.query(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase).options(joinedload(Phases.unidade).joinedload(Unidades.area), selectinload(Phases.interlocks)).all():
        ilk_map = {ilk.numero_interlock: ilk for ilk in ph_obj.interlocks}
        for bit_idx_ilk in range(32):
            il_obj = ilk_map.get(bit_idx_ilk)
            data.append([ph_obj.unidade.area.nome_area, ph_obj.unidade.nome_unidade, ph_obj.nome_phase, bit_idx_ilk, il_obj.seguranca_pt if il_obj else "", il_obj.seguranca_en if il_obj else "", il_obj.seguranca_es if il_obj else "", il_obj.processo_pt if il_obj else "", il_obj.processo_en if il_obj else "", il_obj.processo_es if il_obj else ""])
    return pd.DataFrame(data, columns=['Area', 'Unidade', 'Phase', 'Bit', 'Seg_PT', 'Seg_EN', 'Seg_ES', 'Proc_PT', 'Proc_EN', 'Proc_ES'])
def export_master_transitions(dbsession):
    trans_data_final = []
    csv_header_final = ['Area', 'Unidade', 'Phase', 'Bit_Linha', 'Desc_Linha_PT', 'Desc_Linha_EN', 'Desc_Linha_ES']
    for step_idx_header in range(32): csv_header_final.append(f'Step_{step_idx_header}')
    all_phases_query = dbsession.query(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase).options(joinedload(Phases.unidade).joinedload(Unidades.area), selectinload(Phases.transition_conditions), selectinload(Phases.transition_row_descriptions)).all()
    for phase_obj_loop in all_phases_query:
        cond_map_final = {}
        for cond_obj_loop in phase_obj_loop.transition_conditions:
            if cond_obj_loop.condition_text_pt:
                txt_val = cond_obj_loop.condition_text_pt.strip()
                if cond_obj_loop.condition_logic and cond_obj_loop.condition_logic != 'N/A': txt_val += f" {cond_obj_loop.condition_logic}"
                cond_map_final[(cond_obj_loop.step_index, cond_obj_loop.condition_row)] = txt_val
        desc_map_final = {d.row_number: d for d in phase_obj_loop.transition_row_descriptions}
        for row_idx_trans in range(32):
            d_obj_final = desc_map_final.get(row_idx_trans)
            row_data_final = [phase_obj_loop.unidade.area.nome_area, phase_obj_loop.unidade.nome_unidade, phase_obj_loop.nome_phase, row_idx_trans, d_obj_final.descricao_pt if d_obj_final else "", d_obj_final.descricao_en if d_obj_final else "", d_obj_final.descricao_es if d_obj_final else ""]
            for col_idx_trans in range(32): row_data_final.append(cond_map_final.get((col_idx_trans, row_idx_trans), ""))
            trans_data_final.append(row_data_final)
    return pd.DataFrame(trans_data_final, columns=csv_header_final)

# --- FUNÇÃO IMPORTAÇÃO/MERGE (Mantidas v74) ---
def import_master_excel(dbsession, file_storage):
    dbsession.query(TransitionConditions).delete(); dbsession.query(TransitionRowDescriptions).delete()
    dbsession.query(Passos).delete(); dbsession.query(Parametros).delete()
    dbsession.query(Interlocks).delete(); dbsession.query(Phases).delete()
    dbsession.query(Unidades).delete(); dbsession.query(Areas).delete()
    dbsession.commit()
    try: merge_master_excel(dbsession, io.BytesIO(file_storage.read())) 
    except Exception as e: dbsession.rollback(); raise Exception(f"Erro na importação: {e}")

def merge_master_excel(dbsession, file_storage):
    try:
        if hasattr(file_storage, 'seek'): file_storage.seek(0)
        else: file_storage = io.BytesIO(file_storage.read())
        xls_file = pd.ExcelFile(file_storage)
        ac_obj={a.nome_area:a for a in dbsession.query(Areas).all()}; uc_obj={(u.area.nome_area,u.nome_unidade):u for u in dbsession.query(Unidades).options(joinedload(Unidades.area)).all()}; pc_obj={(p.unidade.area.nome_area,p.unidade.nome_unidade,p.nome_phase):p for p in dbsession.query(Phases).options(joinedload(Phases.unidade).joinedload(Unidades.area)).all()}
        existing_areas_set = set(ac_obj.keys()); existing_units_set = {u_val.nome_unidade for u_val in uc_obj.values()}; existing_phases_set = {(p_val.unidade_id, p_val.nome_phase) for p_val in pc_obj.values()} 
        param_c_set = {(p.phase_id, p.classe_param, p.numero_param) for p in dbsession.query(Parametros.phase_id, Parametros.classe_param, Parametros.numero_param).all()}
        step_c_set = {(s.phase_id, s.numero_passo) for s in dbsession.query(Passos.phase_id, Passos.numero_passo).all()}
        ilk_c_set = {(i.phase_id, i.numero_interlock) for i in dbsession.query(Interlocks.phase_id, Interlocks.numero_interlock).all()}
        trd_c_set = {(d.phase_id, d.row_number) for d in dbsession.query(TransitionRowDescriptions.phase_id, TransitionRowDescriptions.row_number).all()}
        tc_c_set = {(c.phase_id, c.step_index, c.condition_row) for c in dbsession.query(TransitionConditions.phase_id, TransitionConditions.step_index, TransitionConditions.condition_row).all()}

        if 'Areas' in xls_file.sheet_names:
            for _, r_ar in pd.read_excel(xls_file, 'Areas').fillna('').iterrows():
                an_val = str(r_ar.get('Nome_Area', '')).strip()
                if an_val and an_val not in existing_areas_set: a_new=Areas(nome_area=an_val, descricao=r_ar.get('Descricao_Area','')); dbsession.add(a_new); dbsession.flush(); ac_obj[an_val]=a_new; existing_areas_set.add(an_val)
        if 'Unidades' in xls_file.sheet_names:
            for _, r_un in pd.read_excel(xls_file, 'Unidades').fillna('').iterrows():
                an_val, un_val = str(r_un.get('Area', '')).strip(), str(r_un.get('Nome_Unidade', '')).strip()
                if an_val in ac_obj and un_val and un_val not in existing_units_set: u_new=Unidades(nome_unidade=un_val, area_id=ac_obj[an_val].area_id, descricao=r_un.get('Descricao_Unidade','')); dbsession.add(u_new); dbsession.flush(); uc_obj[(an_val,un_val)]=u_new; existing_units_set.add(un_val)
        if 'Phases' in xls_file.sheet_names:
            for _, r_ph in pd.read_excel(xls_file, 'Phases').fillna('').iterrows():
                an_val, un_val, pn_val = str(r_ph.get('Area', '')).strip(), str(r_ph.get('Unidade', '')).strip(), str(r_ph.get('Phase', '')).strip()
                if (an_val,un_val) in uc_obj and pn_val:
                    uid_val = uc_obj[(an_val,un_val)].unidade_id
                    if (uid_val, pn_val) not in existing_phases_set: p_new=Phases(unidade_id=uid_val, nome_phase=pn_val, tipo_phase=r_ph.get('Tipo','PH'), descricao_pt=r_ph.get('Desc_PT'), descricao_en=r_ph.get('Desc_EN'), descricao_es=r_ph.get('Desc_ES')); dbsession.add(p_new); dbsession.flush(); pc_obj[(an_val,un_val,pn_val)]=p_new; existing_phases_set.add((uid_val, pn_val))
        if 'Parametros' in xls_file.sheet_names:
            for _, r_pm in pd.read_excel(xls_file, 'Parametros').fillna('').iterrows():
                k_val = (str(r_pm.get('Area', '')).strip(), str(r_pm.get('Unidade', '')).strip(), str(r_pm.get('Phase', '')).strip())
                if k_val in pc_obj:
                    pid_val = pc_obj[k_val].phase_id; num_val = int(r_pm['Numero']); cls_val = r_pm['Classe']
                    if (pid_val, cls_val, num_val) not in param_c_set: dbsession.add(Parametros(phase_id=pid_val, numero_param=num_val, classe_param=cls_val, nome_param=f"{cls_val}{num_val:03d}", tipo_dado=r_pm['Tipo'], descricao_pt=r_pm.get('Desc_PT'), descricao_en=r_pm.get('Desc_EN'), descricao_es=r_pm.get('Desc_ES'), valor_default=str(r_pm['Default']), valor_min=str(r_pm['Min']), valor_max=str(r_pm['Max']), unidade_engenharia=r_pm.get('Unidade_Eng'))); param_c_set.add((pid_val, cls_val, num_val))
        if 'Passos' in xls_file.sheet_names:
            for _, r_st in pd.read_excel(xls_file, 'Passos').fillna('').iterrows():
                k_val = (str(r_st.get('Area', '')).strip(), str(r_st.get('Unidade', '')).strip(), str(r_st.get('Phase', '')).strip())
                if k_val in pc_obj:
                    pid_val = pc_obj[k_val].phase_id; idx_val = int(r_st['Index'])
                    if (pid_val, idx_val) not in step_c_set: s_new = Passos(phase_id=pid_val, numero_passo=idx_val, codigo_passo=str(r_st['Step_Number']).split('.')[0] if str(r_st['Step_Number'])!='' else None, descricao_pt=r_st.get('Desc_PT'), descricao_en=r_st.get('Desc_EN'), descricao_es=r_st.get('Desc_ES')); dbsession.add(s_new); step_c_set.add((pid_val, idx_val))
        if 'Interlocks' in xls_file.sheet_names:
            for _, r_il in pd.read_excel(xls_file, 'Interlocks').fillna('').iterrows():
                k_val = (str(r_il.get('Area', '')).strip(), str(r_il.get('Unidade', '')).strip(), str(r_il.get('Phase', '')).strip())
                if k_val in pc_obj and str(r_il.get('Bit','')).isdigit():
                    pid_val = pc_obj[k_val].phase_id; bit_val = int(r_il['Bit'])
                    if (pid_val, bit_val) not in ilk_c_set: dbsession.add(Interlocks(phase_id=pid_val, numero_interlock=bit_val, seguranca_pt=r_il.get('Seg_PT'), seguranca_en=r_il.get('Seg_EN'), seguranca_es=r_il.get('Seg_ES'), processo_pt=r_il.get('Proc_PT'), processo_en=r_il.get('Proc_EN'), processo_es=r_il.get('Proc_ES'))); ilk_c_set.add((pid_val, bit_val))
        if 'Transicoes' in xls_file.sheet_names:
            for _, r_tr in pd.read_excel(xls_file, 'Transicoes').fillna('').iterrows():
                k_val = (str(r_tr.get('Area', '')).strip(), str(r_tr.get('Unidade', '')).strip(), str(r_tr.get('Phase', '')).strip())
                if k_val not in pc_obj: continue
                pid_val = pc_obj[k_val].phase_id; rnum_val = int(r_tr['Bit_Linha'])
                if (pid_val, rnum_val) not in trd_c_set and (r_tr.get('Desc_Linha_PT') or r_tr.get('Desc_Linha_EN') or r_tr.get('Desc_Linha_ES')):
                    dbsession.add(TransitionRowDescriptions(phase_id=pid_val, row_number=rnum_val, descricao_pt=r_tr.get('Desc_Linha_PT'), descricao_en=r_tr.get('Desc_Linha_EN'), descricao_es=r_tr.get('Desc_Linha_ES'))); trd_c_set.add((pid_val, rnum_val))
                for step_col_idx_imp in range(32):
                    col_name_tr = f'Step_{step_col_idx_imp}'
                    if col_name_tr in r_tr and str(r_tr[col_name_tr]).strip():
                        if (pid_val, step_col_idx_imp, rnum_val) not in tc_c_set:
                            txt_val, log_val = parse_logic_from_text(r_tr[col_name_tr]); en_val, es_val = auto_translate(txt_val)
                            dbsession.add(TransitionConditions(phase_id=pid_val, step_index=step_col_idx_imp, condition_row=rnum_val, condition_text_pt=txt_val, condition_logic=log_val, condition_text_en=en_val, condition_text_es=es_val)); tc_c_set.add((pid_val, step_col_idx_imp, rnum_val))
        dbsession.commit()
    except Exception as e:
        dbsession.rollback(); raise Exception(f"Erro durante a mesclagem: {e}")

# --- ROTAS ---
@app.route('/', methods=['GET', 'POST'])
def select_project():
    if request.method == 'POST':
        try:
            p_name = request.form.get('project_name')
            if not p_name or ' ' in p_name or '.' in p_name: raise ValueError("Nome inválido.")
            db_path = os.path.join(DATABASE_FOLDER, f"{p_name}.db")
            if not os.path.exists(db_path):
                template_path = os.path.join(basedir, TEMPLATE_DB_NAME)
                if os.path.exists(template_path): shutil.copy(template_path, db_path); flash(f"Projeto '{p_name}' criado via template!", 'success')
                else: engine = create_engine(f'sqlite:///{db_path}'); Base.metadata.create_all(engine); flash(f"Projeto '{p_name}' criado (vazio).", 'warning')
            else: flash(f"Projeto '{p_name}' já existe.", 'error')
        except Exception as e: flash(f"Erro: {e}", 'error')
        return redirect(url_for('select_project'))
    return render_template('select_project.html', projects=[f for f in os.listdir(DATABASE_FOLDER) if f.endswith('.db') and f != TEMPLATE_DB_NAME])

@app.route('/delete_project/<project_name>', methods=['POST'])
def delete_project(project_name):
    try: os.remove(os.path.join(DATABASE_FOLDER, project_name)); flash(f"Projeto '{project_name}' apagado.", 'success')
    except Exception as e: flash(f"Erro: {e}", 'error')
    return redirect(url_for('select_project'))

@app.route('/project/<project_name>/', methods=['GET', 'POST'])
def index(project_name):
    dbsession = get_db_session(project_name)
    if request.method == 'POST':
        try:
            if 'form_import_master' in request.files:
                file = request.files['form_import_master']
                if file.filename.endswith('.xlsx'):
                    try: import_master_excel(dbsession, file); flash("Master Data importado!", 'success')
                    except Exception as e_imp: flash(f"Erro Import: {e_imp}", 'error')
                else: flash("Inválido.", 'error')
            elif 'form_merge_master' in request.files:
                file = request.files['form_merge_master']
                if file.filename.endswith('.xlsx'):
                    try: merge_master_excel(dbsession, file); flash("Master Data mesclado!", 'success')
                    except Exception as e_merge: flash(f"Erro Merge: {e_merge}", 'error')
                else: flash("Inválido.", 'error')
            
            # --- EXPORTAÇÕES COM COOKIE (v85+) ---
            elif 'form_export_master_excel' in request.form:
                output_buffer = io.BytesIO(); writer = pd.ExcelWriter(output_buffer, engine='openpyxl')
                export_master_areas(dbsession).to_excel(writer, 'Areas', index=False); export_master_unidades(dbsession).to_excel(writer, 'Unidades', index=False)
                export_master_phases(dbsession).to_excel(writer, 'Phases', index=False); export_master_params(dbsession).to_excel(writer, 'Parametros', index=False)
                export_master_steps(dbsession).to_excel(writer, 'Passos', index=False); export_master_interlocks(dbsession).to_excel(writer, 'Interlocks', index=False)
                export_master_transitions(dbsession).to_excel(writer, 'Transicoes', index=False)
                writer.close(); output_buffer.seek(0)
                resp = make_response(send_file(output_buffer, as_attachment=True, download_name=f"Master_{project_name}.xlsx", mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
                resp.set_cookie('file_downloaded', 'true', path='/'); return resp
            
            elif 'form_gerar_csv' in request.form:
                root = request.form.get('caminho_raiz_steps'); aid = request.form.get('area_filtrada_id'); uid = request.form.get('unidade_filtrada_id'); tipo = request.form.get('tipo_filtrado')
                q = dbsession.query(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase).options(joinedload(Phases.unidade).joinedload(Unidades.area))
                if aid: q=q.filter(Unidades.area_id==int(aid))
                if uid: q=q.filter(Phases.unidade_id==int(uid))
                if tipo: q=q.filter(Phases.tipo_phase==tipo)
                output_buffer = io.StringIO(); w = csv.writer(output_buffer); w.writerow([":TEMPLATE=$NRK100_Procedure"]); w.writerow([":Tagname","Area","SecurityGroup","ContainedName","ShortDesc","HMIText_StepInformation"])
                for p_arch in q.all():
                    an = p_arch.unidade.area.nome_area
                    w.writerow([f"{an}_{p_arch.nome_phase}", f"{an}_{p_arch.unidade.nome_unidade}", "Default", p_arch.nome_phase, p_arch.nome_phase, f"{root.replace(os.sep,'/')}/{p_arch.unidade.nome_unidade}/{an}_{p_arch.nome_phase}.xml"])
                output_buffer.seek(0)
                resp = make_response(send_file(io.BytesIO(output_buffer.getvalue().encode('utf-8')), as_attachment=True, download_name=f"{project_name}_Phases_Archestra.csv", mimetype='text/csv'))
                resp.set_cookie('file_downloaded', 'true', path='/'); return resp

            elif 'form_gerar_zip' in request.form:
                aid = request.form.get('area_filtrada_id'); uid = request.form.get('unidade_filtrada_id'); tipo = request.form.get('tipo_filtrado')
                q = dbsession.query(Phases).options(joinedload(Phases.unidade).joinedload(Unidades.area))
                if aid: q = q.join(Unidades).filter(Unidades.area_id == int(aid))
                if uid: q = q.filter(Phases.unidade_id == int(uid))
                if tipo: q = q.filter(Phases.tipo_phase == tipo)
                output_buffer = io.BytesIO()
                with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for pz in q.all(): zf.writestr(f"Steps/{pz.unidade.nome_unidade}/{pz.unidade.area.nome_area}_{pz.nome_phase}.xml", generate_steps_xml(pz))
                output_buffer.seek(0)
                resp = make_response(send_file(output_buffer, as_attachment=True, download_name=f"{project_name}_Steps.zip", mimetype='application/zip'))
                resp.set_cookie('file_downloaded', 'true', path='/'); return resp

            elif 'form_gerar_param_csv' in request.form:
                aid = request.form.get('area_filtrada_id'); uid = request.form.get('unidade_filtrada_id'); tipo = request.form.get('tipo_filtrado')
                q = dbsession.query(Parametros).join(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase, Parametros.numero_param).options(joinedload(Parametros.phase).joinedload(Phases.unidade).joinedload(Unidades.area))
                if aid: q = q.filter(Unidades.area_id == int(aid))
                if uid: q = q.filter(Phases.unidade_id == int(uid))
                if tipo: q = q.filter(Phases.tipo_phase == tipo)
                output_buffer = io.StringIO(); w = csv.writer(output_buffer); curr = None
                for pm_arch in q.all():
                    if pm_arch.tipo_dado != curr:
                        if curr: w.writerow([])
                        # v86: Correção de Cabeçalho
                        w.writerow([f":TEMPLATE=$NRK100_Parameter{'Float' if pm_arch.tipo_dado=='real' else 'Integer' if pm_arch.tipo_dado=='inteiro' else 'Bool'}_GEA"])
                        w.writerow([":Tagname","Area","SecurityGroup","Container","ContainedName","Description","ShortDesc","EngUnits","HMIText_ParamDescription.1046","HMIText_ParamDescription.1033","HMIText_ParamDescription.3082","AliasName","ExecutionRelativeOrder","ExecutionRelatedObject"]); curr = pm_arch.tipo_dado
                    d_pt = f"{pm_arch.nome_param}-{pm_arch.descricao_pt or ''}"; d_en = f"{pm_arch.nome_param}-{pm_arch.descricao_en or pm_arch.descricao_pt or ''}"; d_es = f"{pm_arch.nome_param}-{pm_arch.descricao_es or pm_arch.descricao_pt or ''}"
                    w.writerow([f"{pm_arch.phase.unidade.area.nome_area}_{pm_arch.phase.nome_phase}_{pm_arch.nome_param}", f"{pm_arch.phase.unidade.area.nome_area}_{pm_arch.phase.unidade.nome_unidade}", "Default", f"{pm_arch.phase.unidade.area.nome_area}_{pm_arch.phase.nome_phase}", pm_arch.nome_param, d_pt, d_pt, pm_arch.unidade_engenharia or "", d_pt, d_en, d_es, "None", "", ""])
                output_buffer.seek(0)
                resp = make_response(send_file(io.BytesIO(output_buffer.getvalue().encode('utf-8')), as_attachment=True, download_name=f"{project_name}_Params_Archestra.csv", mimetype='text/csv'))
                resp.set_cookie('file_downloaded', 'true', path='/'); return resp

            elif 'form_gerar_interlock_csv' in request.form:
                aid = request.form.get('area_filtrada_id'); uid = request.form.get('unidade_filtrada_id'); tipo = request.form.get('tipo_filtrado')
                q = dbsession.query(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase).options(joinedload(Phases.unidade).joinedload(Unidades.area), selectinload(Phases.interlocks))
                if aid: q = q.filter(Unidades.area_id == int(aid))
                if uid: q = q.filter(Phases.unidade_id == int(uid))
                if tipo: q = q.filter(Phases.tipo_phase == tipo)
                output_buffer = io.StringIO(); w = csv.writer(output_buffer)
                # v86: Correção de Cabeçalho
                w.writerow([":TEMPLATE=$NRK100_Procedure"]); w.writerow([":Tagname","Area","HMIText_SecureInterlocks.1046","HMIText_SecureInterlocks.1033","HMIText_SecureInterlocks.3082","HMIText_ProcessInterlocks.1046","HMIText_ProcessInterlocks.1033","HMIText_ProcessInterlocks.3082"])
                for ph_il in q.all():
                    il_map = {ilk.numero_interlock: ilk for ilk in ph_il.interlocks}; s_pt, s_en, s_es, p_pt, p_en, p_es = [],[],[],[],[],[]
                    for bit_i in range(32):
                        iobj = il_map.get(bit_i)
                        s_pt.append(iobj.seguranca_pt or "" if iobj else ""); s_en.append(iobj.seguranca_en or "" if iobj else ""); s_es.append(iobj.seguranca_es or "" if iobj else "")
                        p_pt.append(iobj.processo_pt or "" if iobj else ""); p_en.append(iobj.processo_en or "" if iobj else ""); p_es.append(iobj.processo_es or "" if iobj else "")
                    w.writerow([f"{ph_il.unidade.area.nome_area}_{ph_il.nome_phase}", f"{ph_il.unidade.area.nome_area}_{ph_il.unidade.nome_unidade}", ",".join(s_pt), ",".join(s_en), ",".join(s_es), ",".join(p_pt), ",".join(p_en), ",".join(p_es)])
                output_buffer.seek(0)
                resp = make_response(send_file(io.BytesIO(output_buffer.getvalue().encode('utf-8')), as_attachment=True, download_name=f"{project_name}_Interlocks_Archestra.csv", mimetype='text/csv'))
                resp.set_cookie('file_downloaded', 'true', path='/'); return resp

            # V88: Revertido para método SÍNCRONO (sem streaming) mas com 'selectinload'
            elif 'form_gerar_transition_csv' in request.form:
                aid = request.form.get('area_filtrada_id'); uid = request.form.get('unidade_filtrada_id'); tipo = request.form.get('tipo_filtrado')
                q = dbsession.query(Phases).join(Unidades).join(Areas).order_by(Areas.nome_area, Unidades.nome_unidade, Phases.nome_phase).options(
                    joinedload(Phases.unidade).joinedload(Unidades.area), 
                    selectinload(Phases.transition_conditions), 
                    selectinload(Phases.transition_row_descriptions)
                )
                if aid: q = q.filter(Unidades.area_id == int(aid))
                if uid: q = q.filter(Phases.unidade_id == int(uid))
                if tipo: q = q.filter(Phases.tipo_phase == tipo)
                
                phases = q.all() # Carrega tudo na memória (otimizado pelo selectinload)
                if not phases: flash("Nada para exportar.", 'error')
                
                output_buffer = io.StringIO(); w = csv.writer(output_buffer); w.writerow([":TEMPLATE=$NRK100_Procedure_Transitions_G"])
                
                # V89: Loop explícito para cabeçalho
                h = [":Tagname","Area","SecurityGroup","Container","ContainedName","Description","ShortDesc"]
                for lc_code_h in ["1033","1046","3082"]:
                    for bit_idx_h in range(32): h.append(f"HMI_ConditionsDescription_{bit_idx_h:02d}.{lc_code_h}")
                for lc_code_h in ["1033","1046","3082"]: h.append(f"HMI_TransitionDescription.{lc_code_h}")
                w.writerow(h)
                
                for p in phases:
                    row = [f"{p.unidade.area.nome_area}_{p.nome_phase}_Tran", f"{p.unidade.area.nome_area}_{p.unidade.nome_unidade}", "Default", f"{p.unidade.area.nome_area}_{p.nome_phase}", "TransitionConditions", "TransitionConditions", "TransitionConditions"]
                    conds = {}; 
                    for c in p.transition_conditions:
                        if c.condition_text_pt:
                            t_val = c.condition_text_pt.strip()
                            if c.condition_logic and c.condition_logic != 'N/A': t_val += f" {c.condition_logic}"
                            conds[(c.step_index, c.condition_row)] = t_val
                    descs = {d.row_number: d for d in p.transition_row_descriptions}
                    
                    # V89: Correção 'lang' -> 'l_code'
                    for l_code in ['en','pt','es']:
                        for s_idx in range(32):
                            lines = []
                            for r_idx in range(32):
                                # V89: Correção para buscar o texto traduzido (se existir)
                                c_obj = conds.get((s_idx, r_idx))
                                txt_val = ""
                                if c_obj:
                                    if l_code == 'en': txt_val = c_obj.condition_text_en
                                    elif l_code == 'pt': txt_val = c_obj.condition_text_pt
                                    else: txt_val = c_obj.condition_text_es
                                    if txt_val and c_obj.condition_logic and c_obj.condition_logic != 'N/A':
                                        txt_val += f" {c_obj.condition_logic}"
                                lines.append(txt_val or "")
                            row.append(",".join(lines))
                    for l_code in ['en','pt','es']:
                        descs_vals = []
                        for r_idx in range(32):
                            d_obj = descs.get(r_idx)
                            val = ""
                            if d_obj:
                                if l_code=='en': val = d_obj.descricao_en
                                elif l_code=='pt': val = d_obj.descricao_pt
                                else: val = d_obj.descricao_es
                            descs_vals.append(val or "")
                        row.append(",".join(descs_vals))
                    w.writerow(row)
                output_buffer.seek(0)
                resp = make_response(send_file(io.BytesIO(output_buffer.getvalue().encode('utf-8')), as_attachment=True, download_name=f"{project_name}_Transitions_Archestra.csv", mimetype='text/csv'))
                resp.set_cookie('file_downloaded', 'true', path='/'); return resp

            elif 'form_remove_area' in request.form:
                 a = dbsession.get(Areas, request.form.get('area_id')); 
                 if a: dbsession.delete(a); dbsession.commit(); flash("Removido.",'success')
            elif 'form_remove_unidade' in request.form:
                 u = dbsession.get(Unidades, request.form.get('unidade_id')); 
                 if u: dbsession.delete(u); dbsession.commit(); flash("Removido.",'success')
            elif 'form_remove_phase' in request.form:
                 p = dbsession.get(Phases, request.form.get('phase_id')); 
                 if p: dbsession.delete(p); dbsession.commit(); flash("Removido.",'success')
        except Exception as e: dbsession.rollback(); flash(f"Erro: {e}", 'error')
        finally: dbsession.close()
        return redirect(url_for('index', project_name=project_name, tipo_filtrado=request.form.get('tipo_filtrado')))

    try:
        aid = request.args.get('area_filtrada_id', type=int); uid = request.args.get('unidade_filtrada_id', type=int); tipo = request.args.get('tipo_filtrado')
        q_u = dbsession.query(Unidades).options(joinedload(Unidades.area)); q_p = dbsession.query(Phases).join(Unidades).join(Areas).options(joinedload(Phases.unidade).joinedload(Unidades.area))
        if aid: q_u=q_u.filter(Unidades.area_id==aid); q_p=q_p.filter(Unidades.area_id==aid)
        if uid: q_p=q_p.filter(Phases.unidade_id==uid)
        if tipo: q_p=q_p.filter(Phases.tipo_phase==tipo)
        phases = q_p.limit(2000).all() if not (aid or uid or tipo) else q_p.all()
        return render_template('index.html', project_name=project_name, todas_areas=dbsession.query(Areas).all(), unidades=q_u.all(), phases=phases, area_filtrada_id=aid, unidade_filtrada_id=uid, tipo_filtrado=tipo)
    finally: dbsession.close()

# --- ROTAS CRUD (INCLUÍDAS) ---
@app.route('/project/<project_name>/add_area', methods=['GET', 'POST'])
def add_area(project_name):
    ds = get_db_session(project_name)
    if request.method == 'POST':
        try: ds.add(Areas(nome_area=request.form['nome_area'])); ds.commit(); return redirect(url_for('index', project_name=project_name))
        except Exception as e: ds.rollback(); flash(f"Erro: {e}", 'error')
    return render_template('add_area.html', project_name=project_name)

@app.route('/project/<project_name>/edit_area/<int:area_id>', methods=['GET', 'POST'])
def edit_area(project_name, area_id):
    ds = get_db_session(project_name); a = ds.get(Areas, area_id)
    if request.method == 'POST':
        try: a.nome_area = request.form.get('nome_area'); ds.commit(); return redirect(url_for('index', project_name=project_name))
        except Exception as e: ds.rollback(); flash(f"Erro: {e}", 'error')
    return render_template('edit_area.html', area=a, project_name=project_name)

@app.route('/project/<project_name>/add_unidade', methods=['GET', 'POST'])
def add_unidade(project_name):
    ds = get_db_session(project_name)
    if request.method == 'POST':
        try: ds.add(Unidades(nome_unidade=request.form['nome_unidade'], area_id=request.form.get('area_id'))); ds.commit(); return redirect(url_for('index', project_name=project_name))
        except Exception as e: ds.rollback(); flash(f"Erro: {e}", 'error')
    return render_template('add_unidade.html', todas_areas=ds.query(Areas).all(), project_name=project_name)

@app.route('/project/<project_name>/edit_unidade/<int:unidade_id>', methods=['GET', 'POST'])
def edit_unidade(project_name, unidade_id):
    ds = get_db_session(project_name); u = ds.get(Unidades, unidade_id)
    if request.method == 'POST':
        try: u.nome_unidade = request.form.get('nome_unidade'); u.area_id = request.form.get('area_id'); ds.commit(); return redirect(url_for('index', project_name=project_name))
        except Exception as e: ds.rollback(); flash(f"Erro: {e}", 'error')
    return render_template('edit_unidade.html', unidade=u, todas_areas=ds.query(Areas).all(), project_name=project_name)

@app.route('/project/<project_name>/add_phase', methods=['GET', 'POST'])
def add_phase(project_name):
    ds = get_db_session(project_name)
    if request.method == 'POST':
        try:
            ds.add(Phases(unidade_id=request.form['unidade_id'], nome_phase=f"{request.form['tipo_phase']}{request.form['nome_phase']}", tipo_phase=request.form['tipo_phase'], descricao_pt=request.form.get('descricao_pt')))
            ds.commit(); return redirect(url_for('index', project_name=project_name))
        except Exception as e: ds.rollback(); flash(f"Erro: {e}", 'error')
    return render_template('add_phase.html', todas_unidades=ds.query(Unidades).options(joinedload(Unidades.area)).all(), project_name=project_name)

@app.route('/project/<project_name>/edit_phase/<int:phase_id>', methods=['GET', 'POST'])
def edit_phase(project_name, phase_id):
    ds = get_db_session(project_name); p = ds.get(Phases, phase_id)
    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo_phase'); nome_input = request.form.get('nome_phase')
            if nome_input.startswith(tipo): nome_input = nome_input[len(tipo):]
            p.nome_phase = f"{tipo}{nome_input}"
            p.tipo_phase = request.form.get('tipo_phase'); p.unidade_id = request.form.get('unidade_id'); p.descricao_pt = request.form.get('descricao_pt')
            p.descricao_en = request.form.get('descricao_en') or auto_translate(p.descricao_pt)[0]; p.descricao_es = request.form.get('descricao_es') or auto_translate(p.descricao_pt)[1]
            ds.commit(); return redirect(url_for('index', project_name=project_name))
        except Exception as e: ds.rollback(); flash(f"Erro: {e}", 'error')
    return render_template('edit_phase.html', phase=p, todas_unidades=ds.query(Unidades).options(joinedload(Unidades.area)).all(), project_name=project_name)

@app.route('/project/<project_name>/phase/<int:phase_id>/', methods=['GET', 'POST'])
def phase_detail(project_name, phase_id):
    ds = get_db_session(project_name)
    phase = ds.query(Phases).options(joinedload(Phases.unidade).joinedload(Unidades.area), selectinload(Phases.parametros), selectinload(Phases.passos), selectinload(Phases.transition_conditions), selectinload(Phases.transition_row_descriptions), selectinload(Phases.interlocks)).get(phase_id)
    if not phase: ds.close(); return "Phase não encontrada", 404
    tab = request.form.get('target_tab', 'parametros') if request.method == 'POST' else request.args.get('tab', 'parametros')

    if request.method == 'POST':
        try:
            if 'form_salvar_parametros' in request.form:
                for pid in request.form.getlist('param_id'):
                    p = ds.get(Parametros, pid)
                    if p and f'delete_param_{pid}' in request.form: ds.delete(p); continue
                    if p:
                        p.numero_param = int(request.form.get(f'numero_param_{pid}')); p.classe_param = request.form.get(f'classe_param_{pid}'); p.nome_param = f"{p.classe_param}{int(p.numero_param):03d}"; p.tipo_dado = request.form.get(f'tipo_dado_{pid}')
                        p.descricao_pt = request.form.get(f'descricao_pt_{pid}'); p.descricao_en = request.form.get(f'descricao_en_{pid}') or auto_translate(p.descricao_pt)[0]; p.descricao_es = request.form.get(f'descricao_es_{pid}') or auto_translate(p.descricao_pt)[1]
                        p.valor_default = request.form.get(f'valor_default_{pid}'); p.valor_min = request.form.get(f'valor_min_{pid}'); p.valor_max = request.form.get(f'valor_max_{pid}'); p.unidade_engenharia = request.form.get(f'unidade_engenharia_{pid}')
                        session['last_classe'] = p.classe_param
                for i_loop, num in enumerate(request.form.getlist('numero_param_new')):
                    if num:
                        cls = request.form.getlist('classe_param_new')[i_loop]; d_pt = request.form.getlist('descricao_pt_new')[i_loop]; en, es = auto_translate(d_pt)
                        ds.add(Parametros(phase_id=phase.phase_id, numero_param=int(num), classe_param=cls, nome_param=f"{cls}{int(num):03d}", tipo_dado=request.form.getlist('tipo_dado_new')[i_loop], descricao_pt=d_pt, descricao_en=en, descricao_es=es, valor_default=request.form.getlist('valor_default_new')[i_loop], valor_min=request.form.getlist('valor_min_new')[i_loop], valor_max=request.form.getlist('valor_max_new')[i_loop], unidade_engenharia=request.form.getlist('unidade_engenharia_new')[i_loop]))
                ds.commit(); flash("Parâmetros salvos.", 'success')
            elif 'form_salvar_passos' in request.form:
                start, end = int(request.form.get('grelha_start')), int(request.form.get('grelha_end'))
                exist = {p.numero_passo: p for p in phase.passos if start <= p.numero_passo < end}
                for i_loop in range(start, end):
                    code, d_pt = request.form.get(f'codigo_passo_{i_loop}'), request.form.get(f'descricao_pt_{i_loop}'); p_obj = exist.get(i_loop)
                    if not code and not d_pt: 
                        if p_obj: ds.delete(p_obj)
                    else:
                        d_en = request.form.get(f'descricao_en_{i_loop}') or auto_translate(d_pt)[0]; d_es = request.form.get(f'descricao_es_{i_loop}') or auto_translate(d_pt)[1]
                        if p_obj: p_obj.codigo_passo = code; p_obj.descricao_pt = d_pt; p_obj.descricao_en = d_en; p_obj.descricao_es = d_es
                        else: ds.add(Passos(phase_id=phase.phase_id, numero_passo=i_loop, codigo_passo=code, descricao_pt=d_pt, descricao_en=d_en, descricao_es=d_es))
                ds.commit(); flash("Passos salvos.", 'success')
            elif 'form_salvar_transicoes' in request.form:
                conds = {(c.step_index, c.condition_row): c for c in phase.transition_conditions}; descs = {d.row_number: d for d in phase.transition_row_descriptions}
                for r_loop in range(32):
                    d_pt = request.form.get(f'trans_row_desc_pt_{r_loop}'); d_obj = descs.get(r_loop)
                    if not d_pt: 
                        if d_obj: ds.delete(d_obj)
                    else:
                        en, es = auto_translate(d_pt)
                        if d_obj: d_obj.descricao_pt = d_pt; d_obj.descricao_en = en; d_obj.descricao_es = es
                        else: ds.add(TransitionRowDescriptions(phase_id=phase.phase_id, row_number=r_loop, descricao_pt=d_pt, descricao_en=en, descricao_es=es))
                    for s_loop in range(32):
                        txt, log = request.form.get(f'trans_text_pt_{s_loop}_{r_loop}'), request.form.get(f'trans_logic_{s_loop}_{r_loop}')
                        c_obj = conds.get((s_loop, r_loop))
                        if not txt and (not log or log=='N/A'): 
                            if c_obj: ds.delete(c_obj)
                        else:
                            en, es = auto_translate(txt)
                            if c_obj: c_obj.condition_text_pt = txt; c_obj.condition_logic = log; c_obj.condition_text_en = en; c_obj.condition_text_es = es
                            else: ds.add(TransitionConditions(phase_id=phase.phase_id, step_index=s_loop, condition_row=r_loop, condition_text_pt=txt, condition_logic=log, condition_text_en=en, condition_text_es=es))
                ds.commit(); flash("Transições salvas.", 'success')
            elif 'form_salvar_interlocks' in request.form:
                ils = {i.numero_interlock: i for i in phase.interlocks}
                for i_loop in range(32):
                    s_pt, p_pt = request.form.get(f'seguranca_pt_{i_loop}'), request.form.get(f'processo_pt_{i_loop}')
                    s_en, s_es = request.form.get(f'seguranca_en_{i_loop}'), request.form.get(f'seguranca_es_{i_loop}')
                    p_en, p_es = request.form.get(f'processo_en_{i_loop}'), request.form.get(f'processo_es_{i_loop}')
                    il_obj = ils.get(i_loop)
                    if not s_pt and not p_pt:
                        if il_obj: ds.delete(il_obj)
                    else:
                        s_en_a, s_es_a = auto_translate(s_pt); p_en_a, p_es_a = auto_translate(p_pt)
                        s_en = s_en or s_en_a; s_es = s_es or s_es_a; p_en = p_en or p_en_a; p_es = p_es or p_es_a
                        if il_obj: il_obj.seguranca_pt=s_pt; il_obj.seguranca_en=s_en; il_obj.seguranca_es=s_es; il_obj.processo_pt=p_pt; il_obj.processo_en=p_en; il_obj.processo_es=p_es
                        else: ds.add(Interlocks(phase_id=phase.phase_id, numero_interlock=i_loop, seguranca_pt=s_pt, seguranca_en=s_en, seguranca_es=s_es, processo_pt=p_pt, processo_en=p_en, processo_es=p_es))
                ds.commit(); flash("Interlocks salvos.", 'success')
        except Exception as e: ds.rollback(); flash(f"Erro: {e}", 'error')
        finally: ds.close()
        return redirect(url_for('phase_detail', project_name=project_name, phase_id=phase_id, tab=tab))

    try:
        trans_grelha = {}
        for c in phase.transition_conditions:
             if c.step_index not in trans_grelha: trans_grelha[c.step_index] = {}
             trans_grelha[c.step_index][c.condition_row] = c
        return render_template('phase_detail.html', project_name=project_name, phase=phase, parametros=phase.parametros, passos_dict={p.numero_passo: p for p in phase.passos}, trans_grelha=trans_grelha, trans_row_descs={d.row_number: d for d in phase.transition_row_descriptions}, interlocks_dict={i.numero_interlock: i for i in phase.interlocks}, last_classe=session.get('last_classe', 'PE'), current_tab=tab)
    finally: ds.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)