@echo off
title LATAM Distributor Service Excellence Assessment
cd /d "%~dp0"
echo Instalando/validando dependencias...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo Iniciando la aplicacion...
streamlit run app.py
pause
