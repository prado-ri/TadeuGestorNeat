@echo off
REM Ativa ambiente virtual se existir
IF EXIST venv\Scripts\activate (
    call venv\Scripts\activate
)

REM Navega até a pasta do projeto
cd SQL Dados

REM Inicia o servidor Flask
start "" http://127.0.0.1:5000
python app.py
