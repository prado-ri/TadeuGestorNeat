import os
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import sessionmaker, relationship, declarative_base

# --- Definição dos Modelos (IDÊNTICA à v68+ do app.py) ---
Base = declarative_base()

class Areas(Base):
    __tablename__ = 'areas'
    area_id = Column(Integer, primary_key=True)
    nome_area = Column(String, nullable=False, unique=True)
    descricao = Column(String)
    unidades = relationship('Unidades', back_populates='area', cascade="all, delete-orphan")

class Unidades(Base):
    __tablename__ = 'unidades'
    unidade_id = Column(Integer, primary_key=True)
    nome_unidade = Column(String, nullable=False, unique=True)
    descricao = Column(String)
    area_id = Column(Integer, ForeignKey('areas.area_id'), nullable=False)
    area = relationship('Areas', back_populates='unidades')
    phases = relationship('Phases', back_populates='unidade', cascade="all, delete-orphan")

class Phases(Base):
    __tablename__ = 'phases'
    phase_id = Column(Integer, primary_key=True)
    nome_phase = Column(String, nullable=False)
    tipo_phase = Column(String, nullable=False)
    descricao_pt = Column(String)
    descricao_en = Column(String)
    descricao_es = Column(String)
    unidade_id = Column(Integer, ForeignKey('unidades.unidade_id'), nullable=False)
    unidade = relationship('Unidades', back_populates='phases')
    parametros = relationship('Parametros', backref='phase', cascade="all, delete-orphan")
    passos = relationship('Passos', backref='phase', cascade="all, delete-orphan")
    # v68: Transições ligadas diretamente à Phase
    transition_conditions = relationship('TransitionConditions', backref='phase', cascade="all, delete-orphan")
    transition_row_descriptions = relationship('TransitionRowDescriptions', backref='phase', cascade="all, delete-orphan")
    interlocks = relationship('Interlocks', backref='phase', cascade="all, delete-orphan")
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
    __table_args__ = (UniqueConstraint('phase_id', 'classe_param', 'numero_param'),)

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
    # v68: Nova estrutura desacoplada
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

# --- Função Principal ---
def criar_nova_base_de_dados(caminho_db):
    """Cria um novo arquivo de banco de dados SQLite com a estrutura correta."""
    try:
        # Garante que a pasta existe
        pasta = os.path.dirname(caminho_db)
        if not os.path.exists(pasta):
            os.makedirs(pasta)

        # Cria a engine e as tabelas
        engine = create_engine(f'sqlite:///{caminho_db}')
        Base.metadata.create_all(engine)
        print(f"Base de dados criada com sucesso em: {caminho_db}")
        return True
    except Exception as e:
        print(f"Erro ao criar base de dados: {e}")
        return False

# Permite testar executando o script diretamente
if __name__ == '__main__':
    criar_nova_base_de_dados('databases/Neat7_template_v68.db')