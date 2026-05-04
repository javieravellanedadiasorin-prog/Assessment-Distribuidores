# LATAM Distributor Service Excellence Assessment

App Streamlit para evaluar el estado del soporte técnico de distribuidores DiaSorin LATAM.

## Funcionalidades principales

- Assessment corporativo editable con todos los puntos del formato base.
- Lista desplegable de distribuidores y países tomada de `data/distributors_master.csv`.
- Selector de periodo con fecha de inicio y fecha de finalización.
- Evaluación de export ISR-Live en CSV/XLSX.
- Validación de Machine Configuration contra valores inválidos como `Don't know`, `Data not available`, `Data no disponible`, `Not done` y campos vacíos.
- Validación de versión de software objetivo por plataforma.
- Workspace por Serial Number para cargar evidencia.
- Análisis inicial de Troubleshooting / TempArchive / LogFile / ErrorFile.
- Exportación a Excel y PDF ejecutivo.
- Tema visual futurista/corporativo.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```

En Windows también puedes ejecutar:

```bash
run_app.bat
```

## Estructura

```text
app.py
requirements.txt
run_app.bat
README.md
.gitignore
.streamlit/config.toml
data/distributors_master.csv
data/distributors_master_latam.csv
```

## Subir a GitHub

```bash
git init
git add .
git commit -m "Initial LATAM Service Assessment app"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/TU-REPOSITORIO.git
git push -u origin main
```

## Nota

La base local `data/service_assessment.db` y la carpeta `evidence/` quedan excluidas del repositorio por `.gitignore` para evitar subir información sensible o archivos pesados.
