# ============================================================
# LATAM Distributor Service Excellence Assessment
# Emergency Stable Build v3.5
# ------------------------------------------------------------
# Objetivo de esta versión:
# 1) Mostrar SIEMPRE todas las preguntas del formato corporativo original.
# 2) Permitir evidencia por cada pregunta.
# 3) Analizar ISR-Live SOLO para el distribuidor seleccionado.
# 4) Mostrar únicamente gráficos ISR-Live solicitados:
#    - Base instalada por modelo.
#    - Machine Configuration completa/incompleta por modelo.
#    - Instrument Status por modelo.
# ============================================================

from __future__ import annotations

import io
import json
import re
import zipfile
from html import escape
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Image as RLImage,
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False



# ============================================================
# Configuración base
# ============================================================

APP_VERSION = "v3.7 - Visible International Technical PDF Build"
BASE_DIR = Path(__file__).parent if "__file__" in globals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
EVIDENCE_DIR = BASE_DIR / "evidence"
EVIDENCE_DIR.mkdir(exist_ok=True)


# ============================================================
# Preguntas originales del formato corporativo
# ============================================================

CORPORATE_QUESTIONS = [
    # Installed Base Certification
    {"id": "IBC-01", "category": "Installed Base Certification", "question": "Installed Base Update", "evidence": "Carta firmada / export ISR-Live actualizado / evidencia de certificación."},
    {"id": "IBC-02", "category": "Installed Base Certification", "question": "System Configuration", "evidence": "CSV ISR-Live o screenshot donde se vea Machine Configuration completa."},
    {"id": "IBC-03", "category": "Installed Base Certification", "question": "Customer Data", "evidence": "Datos de cliente completos: nombre, ciudad, país, dirección si aplica."},
    {"id": "IBC-04", "category": "Installed Base Certification", "question": "System Status", "evidence": "Estado actualizado del instrumento: In routine, Scrapped, Warehouse, Demo, etc."},
    {"id": "IBC-05", "category": "Installed Base Certification", "question": "PM Planner", "evidence": "Evidencia del PM Planner actualizado."},
    {"id": "IBC-06", "category": "Installed Base Certification", "question": "PM Completion Evaluation (%)", "evidence": "Reporte de cumplimiento de PM / service reports."},
    {"id": "IBC-07", "category": "Installed Base Certification", "question": "PM Plan", "evidence": "Plan de mantenimiento preventivo vigente."},
    {"id": "IBC-08", "category": "Installed Base Certification", "question": "PM Kit Stock", "evidence": "Inventario de PM kits disponible para la base instalada."},

    # Contact List
    {"id": "CL-01", "category": "Contact List", "question": "Contacts", "evidence": "Lista actualizada de contactos técnicos, aplicaciones, logística y gerencia."},
    {"id": "CL-02", "category": "Contact List", "question": "FSE and AS Training Status", "evidence": "Matriz de entrenamiento/certificación de FSE y Applications Specialist."},
    {"id": "CL-03", "category": "Contact List", "question": "ISR - Live", "evidence": "Usuarios activos y correctos en ISR-Live."},

    # DiaSorin Accounts Optimization
    {"id": "DAO-01", "category": "DiaSorin Accounts Optimization", "question": "Bomgar", "evidence": "Listado de cuentas BeyondTrust/Bomgar activas y usuarios correctos."},
    {"id": "DAO-02", "category": "DiaSorin Accounts Optimization", "question": "TCM", "evidence": "Validación de accesos TCM activos/correctos."},
    {"id": "DAO-03", "category": "DiaSorin Accounts Optimization", "question": "Apparound", "evidence": "Usuarios Apparound activos/correctos."},
    {"id": "DAO-04", "category": "DiaSorin Accounts Optimization", "question": "Filezilla", "evidence": "Validación de acceso FTPS/FileZilla cuando aplique."},
    {"id": "DAO-05", "category": "DiaSorin Accounts Optimization", "question": "ISR - Live", "evidence": "Validación de usuarios ISR-Live activos/correctos."},
    {"id": "DAO-06", "category": "DiaSorin Accounts Optimization", "question": "RGA Manager", "evidence": "Usuarios activos y evidencia de uso correcto de RGA Manager."},

    # Technical Evaluation
    {"id": "TE-01", "category": "Technical Evaluation", "question": "FSEs", "evidence": "Resultados de exámenes, certificaciones, matriz técnica y brechas."},
    {"id": "TE-02", "category": "Technical Evaluation", "question": "Lead FSE", "evidence": "Validación del Lead FSE, certificación y capacidad de escalación."},

    # Service Tools
    {"id": "ST-01", "category": "Service Tools", "question": "Lubrication Kits", "evidence": "Inventario de lubrication kits y asignación por ingeniero."},
    {"id": "ST-02", "category": "Service Tools", "question": "System Dedicated Tools", "evidence": "Inventario de dedicated tools por plataforma."},
    {"id": "ST-03", "category": "Service Tools", "question": "Service Tools", "evidence": "Inventario general de herramientas de servicio."},
    {"id": "ST-04", "category": "Service Tools", "question": "Bomgar", "evidence": "Evidencia de instalación BeyondTrust/Bomgar en instrumentos activos."},

    # Stock Level
    {"id": "SL-01", "category": "Stock Level", "question": "Data Extraction", "evidence": "Export del inventario de repuestos del distribuidor."},
    {"id": "SL-02", "category": "Stock Level", "question": "Analysis", "evidence": "Análisis de stock vs carstock, consumo, faltantes y partes críticas."},

    # Service Traceability System
    {"id": "STS-01", "category": "Service Traceability System", "question": "Traceability Tool", "evidence": "Herramienta usada para trazabilidad: CRM, ERP, Odoo, sistema interno, etc."},
    {"id": "STS-02", "category": "Service Traceability System", "question": "Service Order Categorization", "evidence": "Evidencia de categorización de órdenes de servicio."},
    {"id": "STS-03", "category": "Service Traceability System", "question": "Data Extraction", "evidence": "Capacidad de extraer reportes de actividades de servicio."},
    {"id": "STS-04", "category": "Service Traceability System", "question": "Activity Tracker", "evidence": "Tracker de actividades, seguimiento de visitas y pendientes."},

    # Customer Visit
    {"id": "CV-01", "category": "Customer Visit", "question": "Customer 1", "evidence": "Evidencia de visita técnica al cliente 1: fotos, service report, hallazgos."},
    {"id": "CV-02", "category": "Customer Visit", "question": "Customer 2", "evidence": "Evidencia de visita técnica al cliente 2: fotos, service report, hallazgos."},
    {"id": "CV-03", "category": "Customer Visit", "question": "Customer 3", "evidence": "Evidencia de visita técnica al cliente 3: fotos, service report, hallazgos."},
    {"id": "IBV-01", "category": "Installed Base Value", "question": "Instrument economic value and spare parts cost to date", "evidence": "Adjuntar archivo del distribuidor con serial number, installation date inicial y costo acumulado en repuestos a la fecha para cada instrumento."},
]


FALLBACK_DISTRIBUTORS = [
    {"Distributor name": "ANNAR", "Country": "Colombia"},
    {"Distributor name": "Bio-Nuclear", "Country": "Dominican Republic"},
    {"Distributor name": "Capris", "Country": "Costa Rica"},
    {"Distributor name": "QLS", "Country": "Panama"},
    {"Distributor name": "Grupo Bios", "Country": "Chile"},
    {"Distributor name": "Diagnóstica Capris Guatemala", "Country": "Guatemala"},
    {"Distributor name": "Diamed Guatemala", "Country": "Guatemala"},
    {"Distributor name": "ARSAL", "Country": "El Salvador"},
    {"Distributor name": "Biotec del Paraguay", "Country": "Paraguay"},
    {"Distributor name": "Cienvar", "Country": "Venezuela"},
    {"Distributor name": "WM Argentina", "Country": "Argentina"},
    {"Distributor name": "Wiener Lab", "Country": "Uruguay"},
    {"Distributor name": "Simed Ecuador", "Country": "Ecuador"},
    {"Distributor name": "Simed Perú", "Country": "Peru"},
    {"Distributor name": "Diagnóstico UAL", "Country": "Peru"},
    {"Distributor name": "Biotec del Perú", "Country": "Peru"},
    {"Distributor name": "Islalab", "Country": "Puerto Rico"},
    {"Distributor name": "Diamed Miami", "Country": "United States"},
]



TECHNICAL_STANDARDS = [
    {
        "code": "NT-01",
        "title": "Installed Base Governance",
        "description": "La base instalada debe estar certificada, trazable y alineada con ISR-Live para el periodo evaluado.",
    },
    {
        "code": "NT-02",
        "title": "Machine Configuration Completa",
        "description": "Machine Configuration debe contener información real del instrumento. No se aceptan campos vacíos, Don't know, Data not available, Not done ni equivalentes.",
    },
    {
        "code": "NT-03",
        "title": "Estado Operativo del Instrumento",
        "description": "Cada instrumento debe tener un estado operativo claro: In routine, Scrapped, Warehouse/Stock, Demo, Removed/Inactive u otro estado verificable.",
    },
    {
        "code": "NT-04",
        "title": "Software y Plataforma",
        "description": "La versión de software debe estar validada contra la versión objetivo vigente definida para cada plataforma y documentada con evidencia.",
    },
    {
        "code": "NT-05",
        "title": "Mantenimiento Preventivo",
        "description": "PM Planner, PM Plan, PM Completion y PM Kit Stock deben estar actualizados y soportados por reportes o evidencias de campo.",
    },
    {
        "code": "NT-06",
        "title": "Capacidad Técnica",
        "description": "El distribuidor debe mantener FSE/AS entrenados, Lead FSE definido y matriz de competencias técnica actualizada.",
    },
    {
        "code": "NT-07",
        "title": "Accesos y Soporte Remoto",
        "description": "Las cuentas y herramientas corporativas autorizadas deben estar actualizadas. Para acceso remoto técnico se debe evidenciar BeyondTrust/Bomgar cuando aplique.",
    },
    {
        "code": "NT-08",
        "title": "Stock, Herramientas y Readiness",
        "description": "El distribuidor debe demostrar disponibilidad de stock crítico, herramientas dedicadas y kits requeridos para garantizar continuidad operativa.",
    },
    {
        "code": "NT-09",
        "title": "Trazabilidad de Servicio y RGA/OBF",
        "description": "Las actividades de servicio, garantías, OBF y RGAs deben estar trazadas en herramientas aprobadas y con evidencia documental.",
    },
    {
        "code": "NT-10",
        "title": "Evidencia de Visitas a Cliente",
        "description": "Las visitas técnicas deben quedar documentadas con service report, fotografías, hallazgos, conclusiones y acciones de seguimiento.",
    },
]

INTERNATIONAL_TECHNICAL_REFERENCES = [
    {
        "reference": "ISO 9001:2015",
        "scope": "Sistema de gestión de calidad",
        "assessment_use": "Base para control documental, trazabilidad, acciones correctivas y mejora continua del soporte técnico.",
    },
    {
        "reference": "ISO 13485:2016",
        "scope": "Sistema de gestión de calidad para dispositivos médicos",
        "assessment_use": "Referencia para documentación de servicio, control de registros, competencia técnica y trazabilidad de actividades sobre equipos IVD.",
    },
    {
        "reference": "ISO 14971:2019",
        "scope": "Gestión de riesgos para dispositivos médicos",
        "assessment_use": "Referencia para clasificar riesgos técnicos, priorizar acciones y documentar mitigaciones.",
    },
    {
        "reference": "ISO 19011:2018",
        "scope": "Directrices para auditoría de sistemas de gestión",
        "assessment_use": "Referencia para estructurar entrevistas, revisión de evidencia y hallazgos del assessment.",
    },
    {
        "reference": "ISO 15189:2022",
        "scope": "Laboratorios médicos - calidad y competencia",
        "assessment_use": "Referencia contextual para trazabilidad, mantenimiento y continuidad operativa en clientes de laboratorio clínico.",
    },
    {
        "reference": "ISO/IEC 17025:2017",
        "scope": "Competencia de laboratorios de ensayo y calibración",
        "assessment_use": "Referencia contextual para control de equipos, registros técnicos y evidencia de verificación/calibración cuando aplique.",
    },
    {
        "reference": "IEC 62304:2006 + AMD1:2015",
        "scope": "Ciclo de vida de software de dispositivos médicos",
        "assessment_use": "Referencia para control de versión de software, evidencia de actualización y trazabilidad de cambios en plataformas diagnósticas.",
    },
    {
        "reference": "IEC 61010-1",
        "scope": "Requisitos de seguridad para equipos eléctricos de medición, control y laboratorio",
        "assessment_use": "Referencia contextual para seguridad eléctrica, condiciones de instalación, mantenimiento y estado físico del instrumento.",
    },
    {
        "reference": "IEC 61326-2-6",
        "scope": "Compatibilidad electromagnética para equipos IVD",
        "assessment_use": "Referencia contextual para condiciones de instalación, ambiente técnico y estabilidad operativa de analizadores IVD.",
    },
    {
        "reference": "ISO 10012:2003",
        "scope": "Sistemas de gestión de las mediciones",
        "assessment_use": "Referencia para control metrológico, herramientas, verificaciones y registros asociados a actividades de servicio.",
    },
]

INVALID_MACHINE_CONFIG_VALUES = {
    "", "-", "--", "n/a", "na", "nan", "none", "null", "no",
    "not available", "data not available", "data no available",
    "data no disponible", "no disponible", "sin informacion", "sin información",
    "dont know", "don't know", "do not know", "unknown", "not done",
    "no hecho", "pendiente", "to be checked", "tbc"
}

COLUMN_SYNONYMS = {
    "distributor": ["Distributor name", "Distributor", "Dealer", "Partner", "Distribuidor", "Nombre distribuidor"],
    "country": ["Country", "Pais", "País"],
    "instrument_type": ["Instrument type", "Instrument Type", "Model", "Analyzer", "Instrument", "Tipo de instrumento", "Modelo"],
    "serial_number": ["Serial number", "Serial Number", "SN", "S/N", "Serial", "N° Serie", "Numero de serie", "Número de serie"],
    "customer_name": ["Customer name", "Customer", "Client", "Hospital/Lab", "Cliente", "Nombre cliente"],
    "city": ["City", "Ciudad"],
    "machine_config": ["Machine Configurations", "Machine Configuration", "Machine config", "Configuration", "Configuración", "Configuracion", "Configuración de máquina", "Configuracion de maquina"],
    "instrument_status": ["Instrument Status", "Status", "Estado", "Estado instrumento", "Operational Status"],
    "software_version": ["Software version", "Software Version", "User SW", "User SW Version", "SW Version", "SW", "Version", "Versión software", "Version software"],
}


# ============================================================
# Estilos
# ============================================================

def inject_css() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at 18% 12%, rgba(0, 229, 255, 0.12), transparent 28%),
                radial-gradient(circle at 85% 20%, rgba(59, 130, 246, 0.16), transparent 30%),
                linear-gradient(135deg, #050814 0%, #08111f 45%, #020617 100%);
            color: #f8fafc;
        }
        .block-container {
            max-width: 1500px;
            padding-top: 1.4rem;
            padding-bottom: 3rem;
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #07111f 0%, #0f172a 100%);
            border-right: 1px solid rgba(34, 211, 238, 0.18);
        }
        .hero {
            padding: 1.6rem 1.8rem;
            border: 1px solid rgba(34, 211, 238, 0.35);
            border-radius: 26px;
            background: linear-gradient(135deg, rgba(8, 47, 73, 0.86), rgba(30, 58, 138, 0.55));
            box-shadow: 0 0 32px rgba(14, 165, 233, 0.22);
            margin-bottom: 1.1rem;
        }
        .hero h1 {
            margin: 0;
            color: #ffffff;
            letter-spacing: -0.03em;
            font-size: 2rem;
        }
        .hero p {
            color: #bae6fd;
            margin-top: .65rem;
            font-size: 1.02rem;
        }
        .pill {
            display: inline-block;
            padding: .25rem .65rem;
            margin-right: .35rem;
            border-radius: 999px;
            border: 1px solid rgba(34, 211, 238, .55);
            color: #a5f3fc;
            background: rgba(8, 47, 73, .38);
            font-size: .78rem;
            font-weight: 700;
        }
        .section-title {
            color: #e0f2fe;
            margin-top: 1.4rem;
            padding-top: .7rem;
            border-top: 1px solid rgba(148, 163, 184, .18);
        }
        .pdf-panel {
            background: linear-gradient(135deg, rgba(0,229,255,.14), rgba(29,78,216,.18));
            border: 1px solid rgba(0,229,255,.40);
            border-radius: 18px;
            padding: 1rem 1.2rem;
            margin: 0.8rem 0 1.1rem 0;
            box-shadow: 0 0 28px rgba(0,229,255,.10);
        }
        .pdf-panel-title {font-weight: 800; font-size: 1.05rem; color: #E0F2FE; margin-bottom: .25rem;}
        .pdf-panel-subtitle {font-size: .88rem; color: #BAE6FD;}
        .question-card {
            padding: 1.05rem 1.15rem;
            margin: .8rem 0 1rem 0;
            border-radius: 22px;
            background: linear-gradient(135deg, rgba(15, 23, 42, .96), rgba(15, 40, 68, .82));
            border: 1px solid rgba(34, 211, 238, .22);
            box-shadow: 0 12px 30px rgba(0, 0, 0, .25);
        }
        .question-id {
            color: #67e8f9;
            font-size: .78rem;
            font-weight: 800;
            letter-spacing: .06em;
            text-transform: uppercase;
        }
        .question-title {
            font-size: 1.08rem;
            font-weight: 800;
            color: #ffffff;
            margin-top: .2rem;
        }
        .evidence-hint {
            color: #cbd5e1;
            font-size: .9rem;
            margin-top: .25rem;
        }
        .metric-card {
            padding: .85rem 1rem;
            border-radius: 18px;
            border: 1px solid rgba(34, 211, 238, .20);
            background: rgba(15, 23, 42, .72);
        }
        .summary-block {
            padding: 1rem 1.1rem;
            border-radius: 18px;
            border: 1px solid rgba(34,211,238,.18);
            background: linear-gradient(135deg, rgba(15,23,42,.88), rgba(8,47,73,.42));
            margin: 1rem 0;
        }
        div[data-testid="stMetricValue"] {font-size: 1.8rem; color: #ecfeff;}
        div[data-testid="stMetricLabel"] {color: #bae6fd;}
        .warning-soft {
            padding: .8rem 1rem;
            border-radius: 16px;
            background: rgba(127, 29, 29, .38);
            border: 1px solid rgba(248, 113, 113, .38);
            color: #fecaca;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        f"""
        <div class="hero">
            <span class="pill">DiaSorin LATAM</span>
            <span class="pill">Technical Support Health Check</span>
            <span class="pill">{APP_VERSION}</span>
            <h1>LATAM Distributor Service Excellence Assessment</h1>
            <p>Assessment corporativo con evidencia por pregunta, análisis ISR-Live y reporte PDF técnico consolidado.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Utilidades de datos
# ============================================================

def normalize_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_key(value) -> str:
    text = normalize_text(value).lower()
    text = text.replace("’", "'").replace("´", "'")
    text = re.sub(r"[^a-z0-9áéíóúñü' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_col(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def detect_column(df: pd.DataFrame, logical_name: str) -> Optional[str]:
    normalized = {normalize_col(c): c for c in df.columns}
    for candidate in COLUMN_SYNONYMS.get(logical_name, []):
        key = normalize_col(candidate)
        if key in normalized:
            return normalized[key]

    flexible_tokens = {
        "distributor": ["distributor"],
        "country": ["country"],
        "instrument_type": ["instrument"],
        "serial_number": ["serial"],
        "customer_name": ["customer"],
        "city": ["city"],
        "machine_config": ["machine", "config"],
        "instrument_status": ["status"],
        "software_version": ["software"],
    }
    tokens = flexible_tokens.get(logical_name, [])
    for col in df.columns:
        low = str(col).lower()
        if all(t in low for t in tokens):
            return col
    return None


def clean_instrument_type(value: str) -> str:
    text = normalize_text(value)
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    low = text.lower()
    if "xl las" in low:
        return "LIAISON XL LAS"
    if "liaison xl" in low or low in {"xl", "lxl"} or " lxl" in low:
        return "LIAISON XL"
    if "liaison xs" in low or low in {"xs", "lxs"} or " lxs" in low:
        return "LIAISON XS"
    return text or "Model not reported"


def machine_config_status(value: str) -> str:
    low = normalize_key(value)
    if low in INVALID_MACHINE_CONFIG_VALUES or len(low) < 3:
        return "Incomplete / invalid"
    return "Complete"


def normalize_status(value: str) -> str:
    text = normalize_text(value)
    low = text.lower()
    if not text:
        return "Status not reported"
    if "routine" in low or "rutina" in low:
        return "In routine"
    if "scrap" in low or "scrapped" in low or "baja" in low:
        return "Scrapped"
    if "warehouse" in low or "stock" in low or "almacen" in low or "almacén" in low:
        return "Warehouse / Stock"
    if "demo" in low:
        return "Demo"
    if "install" in low or "installed" in low or "active" in low:
        return "Installed / Active"
    if "remove" in low or "decommission" in low or "inactive" in low:
        return "Removed / Inactive"
    return text


def read_any_table(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(raw), dtype=str)

    encodings = ["utf-8-sig", "utf-8", "latin1", "cp1252"]
    last_error = None
    for enc in encodings:
        try:
            text = raw.decode(enc)
            sample = text[:4000]
            sep = ";" if sample.count(";") > sample.count(",") else ","
            if "\t" in sample and sample.count("\t") > max(sample.count(";"), sample.count(",")):
                sep = "\t"
            return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, engine="python")
        except Exception as exc:
            last_error = exc
    raise ValueError(f"No fue posible leer el archivo. Último error: {last_error}")


def load_distributors() -> pd.DataFrame:
    paths = [
        DATA_DIR / "distributors_master_latam.csv",
        DATA_DIR / "distributors_master.csv",
        BASE_DIR / "distributors_master_latam.csv",
        BASE_DIR / "distributors_master.csv",
    ]
    for path in paths:
        if path.exists():
            try:
                df = pd.read_csv(path, dtype=str)
                distributor_col = detect_column(df, "distributor") or "Distributor name"
                country_col = detect_column(df, "country") or "Country"
                if distributor_col in df.columns:
                    out = pd.DataFrame()
                    out["Distributor name"] = df[distributor_col].apply(normalize_text)
                    out["Country"] = df[country_col].apply(normalize_text) if country_col in df.columns else ""
                    out = out[out["Distributor name"] != ""].drop_duplicates().sort_values("Distributor name")
                    if not out.empty:
                        return out.reset_index(drop=True)
            except Exception:
                pass
    return pd.DataFrame(FALLBACK_DISTRIBUTORS).drop_duplicates().sort_values("Distributor name").reset_index(drop=True)


def filter_isrlive_by_distributor(df: pd.DataFrame, distributor: str, country: str) -> Tuple[pd.DataFrame, Dict[str, Optional[str]], str]:
    mapping = {k: detect_column(df, k) for k in COLUMN_SYNONYMS}
    dist_col = mapping.get("distributor")
    country_col = mapping.get("country")
    msg = ""

    filtered = df.copy()
    if dist_col:
        target = normalize_key(distributor)
        mask = filtered[dist_col].apply(lambda x: target in normalize_key(x) or normalize_key(x) in target)
        filtered = filtered[mask].copy()
        msg += f"Filtro aplicado por distribuidor usando columna '{dist_col}'. "
    else:
        msg += "No se detectó columna de distribuidor en el archivo; se analiza el archivo cargado completo. "

    if filtered.empty and country_col and country:
        country_target = normalize_key(country)
        mask = df[country_col].apply(lambda x: country_target in normalize_key(x) or normalize_key(x) in country_target)
        filtered = df[mask].copy()
        msg += f"No hubo coincidencia exacta por distribuidor; se aplicó filtro por país usando columna '{country_col}'. "

    return filtered, mapping, msg


def standardize_isrlive(df: pd.DataFrame, mapping: Dict[str, Optional[str]]) -> pd.DataFrame:
    out = pd.DataFrame()
    out["Distributor"] = df[mapping["distributor"]].apply(normalize_text) if mapping.get("distributor") else ""
    out["Country"] = df[mapping["country"]].apply(normalize_text) if mapping.get("country") else ""
    out["Serial Number"] = df[mapping["serial_number"]].apply(normalize_text) if mapping.get("serial_number") else ""
    out["Instrument Model"] = df[mapping["instrument_type"]].apply(clean_instrument_type) if mapping.get("instrument_type") else "Model not reported"
    out["Customer"] = df[mapping["customer_name"]].apply(normalize_text) if mapping.get("customer_name") else ""
    out["City"] = df[mapping["city"]].apply(normalize_text) if mapping.get("city") else ""
    out["Machine Configuration"] = df[mapping["machine_config"]].apply(normalize_text) if mapping.get("machine_config") else ""
    out["Machine Config Status"] = out["Machine Configuration"].apply(machine_config_status)
    out["Instrument Status Original"] = df[mapping["instrument_status"]].apply(normalize_text) if mapping.get("instrument_status") else ""
    out["Instrument Status"] = out["Instrument Status Original"].apply(normalize_status)
    out["Software Version"] = df[mapping["software_version"]].apply(normalize_text) if mapping.get("software_version") else ""
    return out


def save_uploaded_evidence(question_id: str, files) -> List[str]:
    saved = []
    if not files:
        return saved
    q_dir = EVIDENCE_DIR / question_id
    q_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for f in files:
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", f.name)[:140]
        path = q_dir / f"{stamp}_{safe_name}"
        path.write_bytes(f.getvalue())
        saved.append(str(path))
    return saved


def get_question_state(qid: str) -> Dict:
    default = {
        "response": "Pendiente",
        "risk": "Medium",
        "status": "Open",
        "owner": "",
        "due_date": str(date.today()),
        "comments": "",
        "action_plan": "",
        "evidence_note": "",
        "files": [],
    }
    st.session_state.setdefault("assessment_answers", {})
    st.session_state["assessment_answers"].setdefault(qid, default.copy())
    return st.session_state["assessment_answers"][qid]


def score_from_response(response: str) -> Optional[float]:
    if response.startswith("Y"):
        return 1.0
    if response.startswith("P"):
        return 0.5
    if response.startswith("N"):
        return 0.0
    return None


def build_assessment_dataframe() -> pd.DataFrame:
    rows = []
    for q in CORPORATE_QUESTIONS:
        s = get_question_state(q["id"])
        rows.append({
            "ID": q["id"],
            "Category": q["category"],
            "Question": q["question"],
            "Response": s.get("response", "Pendiente"),
            "Score": score_from_response(s.get("response", "Pendiente")),
            "Risk": s.get("risk", ""),
            "Status": s.get("status", ""),
            "Owner": s.get("owner", ""),
            "Due date": s.get("due_date", ""),
            "Comments": s.get("comments", ""),
            "Action plan": s.get("action_plan", ""),
            "Evidence note": s.get("evidence_note", ""),
            "Evidence files": " | ".join(s.get("files", [])),
        })
    return pd.DataFrame(rows)


def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet[:31], index=False)
    return output.getvalue()


def futuristic_layout(fig, title: str, height: int = 430):
    fig.update_layout(
        title=title,
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(2,6,23,0.18)",
        font=dict(color="#E2E8F0"),
        title_font=dict(color="#E0F2FE", size=18),
        legend_title_text="",
        xaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.12)", zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="rgba(148,163,184,0.10)", zeroline=False),
        margin=dict(l=30, r=25, t=65, b=35),
    )
    return fig


def render_expected_vs_obtained_chart(df_assessment: pd.DataFrame) -> None:
    valid = df_assessment.dropna(subset=["Score"]).copy()
    if valid.empty:
        st.info("La gráfica final se habilitará cuando tengas respuestas puntuables en el assessment.")
        return

    cat = valid.groupby("Category", as_index=False)["Score"].mean()
    cat["Obtained"] = (cat["Score"] * 100).round(1)
    cat["Expected"] = 100.0
    cat["Gap"] = (cat["Expected"] - cat["Obtained"]).round(1)
    cat = cat.sort_values("Obtained", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=cat["Category"], x=cat["Expected"], orientation="h",
        name="Esperado",
        marker=dict(color="rgba(148,163,184,0.22)", line=dict(color="rgba(125,211,252,0.40)", width=1.5)),
        text=["100%"] * len(cat), textposition="outside", cliponaxis=False,
        hovertemplate="Categoría: %{y}<br>Esperado: %{x}%<extra></extra>"
    ))
    fig.add_trace(go.Bar(
        y=cat["Category"], x=cat["Obtained"], orientation="h",
        name="Obtenido",
        marker=dict(color="rgba(34,211,238,0.88)", line=dict(color="#22D3EE", width=1.5)),
        text=[f"{v:.1f}%" for v in cat["Obtained"]], textposition="inside",
        hovertemplate="Categoría: %{y}<br>Obtenido: %{x}%<extra></extra>"
    ))
    for _, row in cat.iterrows():
        fig.add_annotation(
            x=100, y=row["Category"],
            text=f"Gap: {row['Gap']:.1f}%",
            xanchor="left", yanchor="middle", showarrow=False,
            font=dict(color="#F8FAFC", size=11), bgcolor="rgba(15,23,42,0.35)"
        )
    fig.update_layout(barmode="overlay", xaxis_title="Cumplimiento (%)", yaxis_title="", bargap=0.30)
    fig.update_xaxes(range=[0, 115])
    futuristic_layout(fig, "Resultado esperado vs obtenido por categoría", height=520)
    st.plotly_chart(fig, use_container_width=True)


def render_sidebar_pdf_panel(container, distributor: str, country: str, start_date: date, end_date: date) -> None:
    with container:
        st.markdown("### Informe técnico PDF")
        st.caption("Generador consolidado del assessment y las evidencias de la sesión.")
        if REPORTLAB_AVAILABLE:
            try:
                pdf_bytes = create_technical_pdf_report(distributor, country, start_date, end_date)
                st.download_button(
                    "📄 Descargar PDF técnico",
                    data=pdf_bytes,
                    file_name=f"Technical_Assessment_Report_{distributor}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf".replace(" ", "_"),
                    mime="application/pdf",
                    use_container_width=True,
                    key="sidebar_pdf_download",
                )
            except Exception as exc:
                st.error(f"No fue posible generar el PDF: {exc}")
        else:
            st.error("No se puede generar el PDF porque falta ReportLab en requirements.txt.")


# ============================================================
# Sidebar
# ============================================================

def sidebar_context() -> Tuple[str, str, date, date, object]:
    distributors_df = load_distributors()
    distributors = distributors_df["Distributor name"].dropna().astype(str).sort_values().unique().tolist()

    st.sidebar.markdown("### Contexto del assessment")
    selected_distributor = st.sidebar.selectbox("Distribuidor", distributors, index=0)
    countries = distributors_df.loc[distributors_df["Distributor name"] == selected_distributor, "Country"].dropna().astype(str).unique().tolist()
    selected_country = countries[0] if countries else ""
    selected_country = st.sidebar.text_input("País", value=selected_country)

    st.sidebar.markdown("### Periodo evaluado")
    start_date = st.sidebar.date_input("Fecha de inicio", value=date(date.today().year, 1, 1))
    end_date = st.sidebar.date_input("Fecha de finalización", value=date.today())
    if end_date < start_date:
        st.sidebar.error("La fecha final no puede ser anterior a la fecha inicial.")

    pdf_container = st.sidebar.container()

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Build activo: {APP_VERSION}")
    st.session_state["selected_distributor"] = selected_distributor
    st.session_state["selected_country"] = selected_country
    st.session_state["period_start"] = str(start_date)
    st.session_state["period_end"] = str(end_date)
    return selected_distributor, selected_country, start_date, end_date, pdf_container


# ============================================================
# Páginas
# ============================================================

def page_corporate_assessment(distributor: str, country: str, start_date: date, end_date: date) -> None:
    st.subheader("Assessment corporativo completo")
    st.caption("Se mantiene el formato del assessment y se agregan campos de evidencia por pregunta. También se añadió el punto de valor acumulado por instrumento.")

    df_assessment = build_assessment_dataframe()
    valid_scores = df_assessment["Score"].dropna()
    global_score = round(valid_scores.mean() * 100, 1) if len(valid_scores) else 0
    completed = int(df_assessment["Response"].str.startswith(("Y", "P", "N"), na=False).sum())
    evidence_count = sum(len(get_question_state(q["id"]).get("files", [])) for q in CORPORATE_QUESTIONS)
    open_items = int(df_assessment["Status"].isin(["Open", "In progress", "Overdue"]).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score corporativo", f"{global_score}%")
    c2.metric("Preguntas respondidas", f"{completed}/{len(CORPORATE_QUESTIONS)}")
    c3.metric("Evidencias cargadas", evidence_count)
    c4.metric("Pendientes abiertos", open_items)

    st.markdown(
        f"""
        <div class="summary-block">
            <b>Contexto vigente:</b> {distributor} · {country} · Periodo {start_date} a {end_date}.<br>
            <span style="color:#BAE6FD;">El botón del PDF técnico ahora está en la barra lateral izquierda, justo debajo del contexto del assessment.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    categories = list(dict.fromkeys(q["category"] for q in CORPORATE_QUESTIONS))
    for category in categories:
        st.markdown(f"<h3 class='section-title'>{category}</h3>", unsafe_allow_html=True)
        for q in [x for x in CORPORATE_QUESTIONS if x["category"] == category]:
            render_question_card(q)

    df_assessment = build_assessment_dataframe()
    st.markdown("### Gráfica final del assessment")
    st.caption("Comparación visual entre lo esperado (100%) y lo obtenido por categoría, con estilo futurista y lectura más ejecutiva.")
    render_expected_vs_obtained_chart(df_assessment)

    meta = pd.DataFrame([{
        "Distributor": distributor,
        "Country": country,
        "Period start": str(start_date),
        "Period end": str(end_date),
        "Generated at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Build": APP_VERSION,
        "Global score": global_score,
    }])
    excel_bytes = to_excel_bytes({"Summary": meta, "Corporate Assessment": df_assessment})
    st.download_button(
        "Descargar assessment en Excel",
        data=excel_bytes,
        file_name=f"Corporate_Assessment_{distributor}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx".replace(" ", "_"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_assessment_excel",
    )


def render_question_card(q: Dict) -> None:
    state = get_question_state(q["id"])
    st.markdown(
        f"""
        <div class="question-card">
            <div class="question-id">{q['id']} · {q['category']}</div>
            <div class="question-title">{q['question']}</div>
            <div class="evidence-hint"><b>Evidencia esperada:</b> {q['evidence']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        c1, c2, c3, c4 = st.columns([1.25, 1, 1, 1.15])
        state["response"] = c1.selectbox(
            "Respuesta",
            ["Pendiente", "Y - Cumple", "P - Parcial", "N - No cumple", "NA - No aplica"],
            index=["Pendiente", "Y - Cumple", "P - Parcial", "N - No cumple", "NA - No aplica"].index(state.get("response", "Pendiente")),
            key=f"resp_{q['id']}",
        )
        state["risk"] = c2.selectbox(
            "Riesgo",
            ["Low", "Medium", "High", "Critical"],
            index=["Low", "Medium", "High", "Critical"].index(state.get("risk", "Medium")),
            key=f"risk_{q['id']}",
        )
        state["status"] = c3.selectbox(
            "Estado",
            ["Open", "In progress", "Closed", "Overdue", "Not applicable"],
            index=["Open", "In progress", "Closed", "Overdue", "Not applicable"].index(state.get("status", "Open")),
            key=f"status_{q['id']}",
        )
        due_value = state.get("due_date", str(date.today()))
        try:
            due_date_obj = datetime.strptime(due_value, "%Y-%m-%d").date()
        except Exception:
            due_date_obj = date.today()
        state["due_date"] = str(c4.date_input("Fecha compromiso", value=due_date_obj, key=f"due_{q['id']}"))

        c5, c6 = st.columns([1, 2])
        state["owner"] = c5.text_input("Responsable", value=state.get("owner", ""), key=f"owner_{q['id']}")
        state["evidence_note"] = c6.text_input("Nota de evidencia", value=state.get("evidence_note", ""), key=f"evnote_{q['id']}")

        c7, c8 = st.columns(2)
        state["comments"] = c7.text_area("Comentarios", value=state.get("comments", ""), height=80, key=f"comments_{q['id']}")
        state["action_plan"] = c8.text_area("Plan de acción", value=state.get("action_plan", ""), height=80, key=f"action_{q['id']}")

        files = st.file_uploader(
            "Subir evidencia para esta pregunta",
            type=["png", "jpg", "jpeg", "pdf", "xlsx", "xls", "csv", "txt", "zip", "docx", "pptx"],
            accept_multiple_files=True,
            key=f"file_{q['id']}",
        )
        if files:
            if st.button(f"Guardar evidencia {q['id']}", key=f"savefiles_{q['id']}"):
                saved = save_uploaded_evidence(q["id"], files)
                state.setdefault("files", [])
                state["files"].extend(saved)
                st.success(f"Evidencia guardada: {len(saved)} archivo(s).")

        if state.get("files"):
            with st.expander(f"Evidencias guardadas para {q['id']} ({len(state['files'])})", expanded=False):
                for path in state["files"]:
                    st.write(path)

    st.session_state["assessment_answers"][q["id"]] = state


def page_isrlive(distributor: str, country: str) -> None:
    st.subheader("Análisis ISR-Live por distribuidor")
    st.caption("Carga el CSV/XLSX de ISR-Live. El análisis se filtra al distribuidor seleccionado en la barra lateral.")

    uploaded = st.file_uploader("Subir archivo ISR-Live", type=["csv", "xlsx", "xls"], accept_multiple_files=False, key="isrlive_file")
    if not uploaded:
        st.info("Carga un archivo ISR-Live para visualizar base instalada, Machine Configuration y status por modelo.")
        return

    try:
        raw_df = read_any_table(uploaded)
    except Exception as exc:
        st.error(f"No pude leer el archivo: {exc}")
        return

    if raw_df.empty:
        st.warning("El archivo cargado está vacío.")
        return

    filtered, mapping, msg = filter_isrlive_by_distributor(raw_df, distributor, country)
    if msg:
        st.caption(msg)

    if filtered.empty:
        st.error(f"No encontré registros para el distribuidor seleccionado: {distributor} / {country}.")
        possible_col = mapping.get("distributor")
        if possible_col:
            detected = raw_df[possible_col].dropna().astype(str).drop_duplicates().sort_values().head(80)
            st.write("Distribuidores detectados en el archivo:")
            st.dataframe(pd.DataFrame({"Distributor detected": detected}), use_container_width=True, hide_index=True)
        return

    std = standardize_isrlive(filtered, mapping)
    st.session_state["last_isrlive_std"] = std

    total = len(std)
    models = std["Instrument Model"].nunique()
    mc_incomplete = int((std["Machine Config Status"] == "Incomplete / invalid").sum())
    statuses = std["Instrument Status"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros del distribuidor", total)
    c2.metric("Modelos", models)
    c3.metric("Machine Config incompleta", mc_incomplete)
    c4.metric("Estados detectados", statuses)

    render_isrlive_charts(std)

    st.markdown("### Detalle ISR-Live filtrado")
    st.dataframe(std, use_container_width=True, hide_index=True)

    bad = std[std["Machine Config Status"] == "Incomplete / invalid"].copy()
    st.markdown("### Equipos con Machine Configuration incompleta / inválida")
    if bad.empty:
        st.success("No se detectaron Machine Configuration inválidas en el distribuidor seleccionado.")
    else:
        st.dataframe(bad, use_container_width=True, hide_index=True)

    excel_bytes = to_excel_bytes({"ISR Filtered": std, "Machine Config Issues": bad})
    st.download_button(
        "Descargar análisis ISR-Live filtrado",
        data=excel_bytes,
        file_name=f"ISRLive_Analysis_{distributor}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx".replace(" ", "_"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def render_isrlive_charts(std: pd.DataFrame) -> None:
    st.markdown("### Base instalada por modelo")
    by_model = std.groupby("Instrument Model", as_index=False).size().rename(columns={"size": "Installed Base"})
    fig1 = px.bar(
        by_model, x="Instrument Model", y="Installed Base", text="Installed Base",
        color="Instrument Model", color_discrete_sequence=["rgba(34,211,238,0.85)", "rgba(59,130,246,0.82)", "rgba(16,185,129,0.82)", "rgba(168,85,247,0.82)"]
    )
    futuristic_layout(fig1, "Base instalada por modelo", height=420)
    fig1.update_traces(marker_line_color="rgba(224,242,254,0.25)", marker_line_width=1.2, textposition="outside")
    fig1.update_xaxes(title_text="Modelo")
    fig1.update_yaxes(title_text="Cantidad")
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("### Machine Configuration por modelo")
    mc = std.groupby(["Instrument Model", "Machine Config Status"], as_index=False).size().rename(columns={"size": "Count"})
    fig2 = px.bar(
        mc, x="Instrument Model", y="Count", color="Machine Config Status", text="Count", barmode="group",
        color_discrete_map={"Complete": "rgba(16,185,129,0.85)", "Incomplete / invalid": "rgba(248,113,113,0.88)"}
    )
    futuristic_layout(fig2, "Machine Configuration: completo vs incompleto por modelo", height=440)
    fig2.update_traces(marker_line_color="rgba(224,242,254,0.28)", marker_line_width=1.2)
    fig2.update_xaxes(title_text="Modelo")
    fig2.update_yaxes(title_text="Cantidad")
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### Instrument Status por modelo")
    st_df = std.groupby(["Instrument Model", "Instrument Status"], as_index=False).size().rename(columns={"size": "Count"})
    fig3 = px.bar(
        st_df, x="Instrument Model", y="Count", color="Instrument Status", text="Count", barmode="stack",
        color_discrete_sequence=["rgba(34,211,238,0.85)", "rgba(59,130,246,0.82)", "rgba(16,185,129,0.82)", "rgba(251,191,36,0.82)", "rgba(248,113,113,0.84)", "rgba(168,85,247,0.84)", "rgba(148,163,184,0.80)"]
    )
    futuristic_layout(fig3, "Instrument Status por modelo", height=480)
    fig3.update_traces(marker_line_color="rgba(224,242,254,0.18)", marker_line_width=1.0)
    fig3.update_xaxes(title_text="Modelo")
    fig3.update_yaxes(title_text="Cantidad")
    st.plotly_chart(fig3, use_container_width=True)


# ============================================================
# Reporte PDF tecnico
# ============================================================

def pdf_safe(value) -> str:
    """Texto seguro para ReportLab con fuentes estándar."""
    text = normalize_text(value)
    text = text.replace("–", "-").replace("—", "-").replace("•", "-")
    text = text.replace("✅", "OK").replace("❌", "NO").replace("⚪", "N/A")
    return text.encode("latin-1", "replace").decode("latin-1")


def ptxt(value) -> str:
    return escape(pdf_safe(value)).replace("\n", "<br/>")


def evidence_basename(path: str) -> str:
    try:
        return Path(path).name
    except Exception:
        return str(path)


def is_image_path(path: str) -> bool:
    return str(path).lower().endswith((".png", ".jpg", ".jpeg")) and Path(path).exists()


def get_pdf_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CoverTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        name="CoverSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#334155"),
        spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        name="SectionHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#075985"),
        spaceBefore=12,
        spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="SmallText",
        parent=styles["Normal"],
        fontSize=7.4,
        leading=9,
        textColor=colors.HexColor("#0F172A"),
    ))
    styles.add(ParagraphStyle(
        name="TinyText",
        parent=styles["Normal"],
        fontSize=6.4,
        leading=7.6,
        textColor=colors.HexColor("#334155"),
    ))
    styles.add(ParagraphStyle(
        name="FindingText",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#111827"),
        spaceAfter=4,
    ))
    return styles


def add_table_style(table: Table, header_color: str = "#0F172A") -> Table:
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7.2),
        ("FONTSIZE", (0, 1), (-1, -1), 6.8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def dataframe_to_pdf_table(df: pd.DataFrame, columns: List[str], styles, max_rows: int = 40, widths: Optional[List[float]] = None, header_color: str = "#0F172A") -> Table:
    if df is None or df.empty:
        df = pd.DataFrame(columns=columns)
    display = df.copy()
    for col in columns:
        if col not in display.columns:
            display[col] = ""
    display = display[columns].head(max_rows).fillna("")
    rows = [[Paragraph(ptxt(col), styles["TinyText"]) for col in columns]]
    for _, row in display.iterrows():
        rows.append([Paragraph(ptxt(row.get(col, "")), styles["TinyText"]) for col in columns])
    if widths is None:
        widths = [17 * cm / max(1, len(columns))] * len(columns)
    return add_table_style(Table(rows, colWidths=widths, repeatRows=1), header_color=header_color)


def risk_summary_text(global_score: float, assessment: pd.DataFrame, isr: pd.DataFrame) -> str:
    open_items = 0
    critical_items = 0
    if assessment is not None and not assessment.empty:
        open_items = int(assessment[assessment["Status"].isin(["Open", "In progress", "Overdue"])].shape[0])
        critical_items = int((assessment["Risk"] == "Critical").sum())
    mc_issues = 0
    if isinstance(isr, pd.DataFrame) and not isr.empty and "Machine Config Status" in isr.columns:
        mc_issues = int((isr["Machine Config Status"] == "Incomplete / invalid").sum())

    if global_score >= 90 and critical_items == 0 and mc_issues == 0:
        conclusion = "El distribuidor evidencia un nivel de control tecnico alto para el periodo evaluado."
    elif global_score >= 75:
        conclusion = "El distribuidor evidencia un nivel controlado, con acciones de seguimiento que deben cerrarse para robustecer la trazabilidad."
    elif global_score >= 60:
        conclusion = "El distribuidor presenta brechas relevantes que requieren plan de accion formal y seguimiento cercano."
    else:
        conclusion = "El distribuidor presenta un riesgo operativo alto; se recomienda intervencion prioritaria y seguimiento ejecutivo."

    return (
        f"Score corporativo: {global_score}%. Items abiertos/en progreso/vencidos: {open_items}. "
        f"Items criticos: {critical_items}. Equipos con Machine Configuration incompleta o invalida: {mc_issues}. "
        f"{conclusion}"
    )


def create_technical_pdf_report(distributor: str, country: str, start_date: date, end_date: date) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("ReportLab no esta disponible. Agrega 'reportlab' a requirements.txt.")

    assessment = build_assessment_dataframe()
    isr = st.session_state.get("last_isrlive_std", pd.DataFrame())
    valid_scores = assessment["Score"].dropna()
    global_score = round(valid_scores.mean() * 100, 1) if len(valid_scores) else 0
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    evidence_count = sum(len(get_question_state(q["id"]).get("files", [])) for q in CORPORATE_QUESTIONS)
    completed = int(assessment["Response"].str.startswith(("Y", "P", "N"), na=False).sum())

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=1.15 * cm,
        rightMargin=1.15 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
        title=f"Technical Assessment Report - {distributor}",
        author="DiaSorin LATAM Service",
    )
    styles = get_pdf_styles()
    story = []

    # Portada / resumen
    story.append(Paragraph("LATAM Distributor Service Excellence Assessment", styles["CoverTitle"]))
    story.append(Paragraph("Technical Assessment Report - Normas tecnicas, resultados, evidencias y hallazgos", styles["CoverSubtitle"]))

    meta_rows = [
        ["Distribuidor", distributor, "Pais", country],
        ["Periodo evaluado", f"{start_date} a {end_date}", "Fecha de generacion", generated_at],
        ["Build", APP_VERSION, "Score corporativo", f"{global_score}%"],
        ["Preguntas respondidas", f"{completed}/{len(CORPORATE_QUESTIONS)}", "Evidencias cargadas", str(evidence_count)],
    ]
    meta_table = Table([[Paragraph(ptxt(c), styles["SmallText"]) for c in row] for row in meta_rows], colWidths=[3.4 * cm, 5.0 * cm, 3.4 * cm, 5.0 * cm])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#93C5FD")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Conclusion tecnica ejecutiva", styles["SectionHeader"]))
    story.append(Paragraph(ptxt(risk_summary_text(global_score, assessment, isr)), styles["FindingText"]))

    # Normas tecnicas / criterios
    story.append(Paragraph("Normas tecnicas y criterios de evaluacion", styles["SectionHeader"]))
    standards_rows = [["Codigo", "Criterio tecnico", "Descripcion"]]
    for item in TECHNICAL_STANDARDS:
        standards_rows.append([item["code"], item["title"], item["description"]])
    standards_table = Table(
        [[Paragraph(ptxt(c), styles["TinyText"]) for c in row] for row in standards_rows],
        colWidths=[1.7 * cm, 4.2 * cm, 11.0 * cm],
        repeatRows=1,
    )
    story.append(add_table_style(standards_table, header_color="#075985"))

    story.append(Spacer(1, 0.25 * cm))
    story.append(Paragraph("Referencias tecnicas internacionales aplicables", styles["SectionHeader"]))
    story.append(Paragraph(
        "Las siguientes referencias se incluyen como marco tecnico internacional de buenas practicas para calidad, trazabilidad, competencia, riesgo y control de equipos IVD. Este assessment no certifica cumplimiento normativo; documenta evidencia operativa para gestion tecnica del distribuidor.",
        styles["FindingText"],
    ))
    intl_rows = [["Referencia", "Alcance", "Uso dentro del assessment"]]
    for ref in INTERNATIONAL_TECHNICAL_REFERENCES:
        intl_rows.append([ref["reference"], ref["scope"], ref["assessment_use"]])
    intl_table = Table(
        [[Paragraph(ptxt(c), styles["TinyText"]) for c in row] for row in intl_rows],
        colWidths=[3.2 * cm, 4.6 * cm, 9.0 * cm],
        repeatRows=1,
    )
    story.append(add_table_style(intl_table, header_color="#155E75"))

    # Score por categoria
    story.append(Paragraph("Resultado por categoria", styles["SectionHeader"]))
    if not assessment.dropna(subset=["Score"]).empty:
        cat_score = assessment.dropna(subset=["Score"]).groupby("Category", as_index=False)["Score"].mean()
        cat_score["Score %"] = (cat_score["Score"] * 100).round(1)
        cat_score = cat_score[["Category", "Score %"]]
        story.append(dataframe_to_pdf_table(cat_score, ["Category", "Score %"], styles, max_rows=50, widths=[12.5 * cm, 3.5 * cm], header_color="#0F766E"))
    else:
        story.append(Paragraph("No hay respuestas puntuables registradas aun.", styles["FindingText"]))

    # Assessment completo
    story.append(PageBreak())
    story.append(Paragraph("Assessment corporativo completo", styles["SectionHeader"]))
    assessment_cols = ["ID", "Category", "Question", "Response", "Risk", "Status", "Owner", "Due date", "Comments", "Action plan", "Evidence note"]
    story.append(dataframe_to_pdf_table(
        assessment,
        assessment_cols,
        styles,
        max_rows=100,
        widths=[1.3 * cm, 2.7 * cm, 3.2 * cm, 2.0 * cm, 1.6 * cm, 1.8 * cm, 2.1 * cm, 1.8 * cm, 3.2 * cm, 3.2 * cm, 2.8 * cm],
        header_color="#1E3A8A",
    ))

    # Evidencias
    story.append(PageBreak())
    story.append(Paragraph("Evidencias por pregunta", styles["SectionHeader"]))
    any_evidence = False
    image_counter = 0
    max_images = 24
    for q in CORPORATE_QUESTIONS:
        state = get_question_state(q["id"])
        files = state.get("files", [])
        if not files:
            continue
        any_evidence = True
        story.append(KeepTogether([
            Paragraph(f"<b>{ptxt(q['id'])} - {ptxt(q['question'])}</b>", styles["FindingText"]),
            Paragraph(f"Evidencia esperada: {ptxt(q['evidence'])}", styles["TinyText"]),
            Paragraph(f"Nota registrada: {ptxt(state.get('evidence_note', ''))}", styles["TinyText"]),
        ]))
        evidence_rows = [["Archivo", "Tipo", "Incluido visualmente"]]
        for path in files:
            suffix = Path(path).suffix.lower().replace(".", "") or "archivo"
            included = "Imagen adjunta en el reporte" if is_image_path(path) and image_counter < max_images else "Listado documental"
            evidence_rows.append([evidence_basename(path), suffix.upper(), included])
        evidence_table = Table(
            [[Paragraph(ptxt(c), styles["TinyText"]) for c in row] for row in evidence_rows],
            colWidths=[9.0 * cm, 2.0 * cm, 5.2 * cm],
            repeatRows=1,
        )
        story.append(add_table_style(evidence_table, header_color="#334155"))
        story.append(Spacer(1, 0.12 * cm))

        # Inserta thumbnails de imagenes cargadas
        image_paths = [path for path in files if is_image_path(path)]
        if image_paths and image_counter < max_images:
            img_cells = []
            row_cells = []
            for path in image_paths:
                if image_counter >= max_images:
                    break
                try:
                    img = RLImage(path)
                    max_w = 5.1 * cm
                    max_h = 3.7 * cm
                    ratio = min(max_w / float(img.imageWidth), max_h / float(img.imageHeight))
                    img.drawWidth = float(img.imageWidth) * ratio
                    img.drawHeight = float(img.imageHeight) * ratio
                    cell = [img, Paragraph(ptxt(evidence_basename(path)), styles["TinyText"])]
                    row_cells.append(cell)
                    image_counter += 1
                    if len(row_cells) == 3:
                        img_cells.append(row_cells)
                        row_cells = []
                except Exception:
                    continue
            if row_cells:
                while len(row_cells) < 3:
                    row_cells.append("")
                img_cells.append(row_cells)
            if img_cells:
                img_table = Table(img_cells, colWidths=[5.4 * cm, 5.4 * cm, 5.4 * cm])
                img_table.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(img_table)
        story.append(Spacer(1, 0.25 * cm))
    if not any_evidence:
        story.append(Paragraph("No hay evidencias cargadas en la sesion actual. El reporte deja trazabilidad de resultados y hallazgos, pero no adjunta archivos.", styles["FindingText"]))

    # ISR-Live
    story.append(PageBreak())
    story.append(Paragraph("Analisis ISR-Live del distribuidor seleccionado", styles["SectionHeader"]))
    if isinstance(isr, pd.DataFrame) and not isr.empty:
        by_model = isr.groupby("Instrument Model", as_index=False).size().rename(columns={"size": "Installed Base"})
        story.append(Paragraph("Base instalada por modelo", styles["FindingText"]))
        story.append(dataframe_to_pdf_table(by_model, ["Instrument Model", "Installed Base"], styles, max_rows=30, widths=[11.5 * cm, 4.0 * cm], header_color="#075985"))
        story.append(Spacer(1, 0.18 * cm))

        mc = isr.groupby(["Instrument Model", "Machine Config Status"], as_index=False).size().rename(columns={"size": "Count"})
        story.append(Paragraph("Machine Configuration por modelo", styles["FindingText"]))
        story.append(dataframe_to_pdf_table(mc, ["Instrument Model", "Machine Config Status", "Count"], styles, max_rows=60, widths=[6.3 * cm, 6.3 * cm, 3.0 * cm], header_color="#0F766E"))
        story.append(Spacer(1, 0.18 * cm))

        status_df = isr.groupby(["Instrument Model", "Instrument Status"], as_index=False).size().rename(columns={"size": "Count"})
        story.append(Paragraph("Instrument Status por modelo", styles["FindingText"]))
        story.append(dataframe_to_pdf_table(status_df, ["Instrument Model", "Instrument Status", "Count"], styles, max_rows=80, widths=[6.3 * cm, 6.3 * cm, 3.0 * cm], header_color="#1E3A8A"))
        story.append(Spacer(1, 0.18 * cm))

        bad = isr[isr["Machine Config Status"] == "Incomplete / invalid"].copy()
        story.append(Paragraph("Equipos con Machine Configuration incompleta o invalida", styles["FindingText"]))
        if bad.empty:
            story.append(Paragraph("No se detectaron Machine Configuration invalidas para el distribuidor seleccionado.", styles["SmallText"]))
        else:
            story.append(dataframe_to_pdf_table(
                bad,
                ["Serial Number", "Instrument Model", "Customer", "City", "Instrument Status", "Machine Configuration", "Software Version"],
                styles,
                max_rows=80,
                widths=[2.4 * cm, 2.7 * cm, 3.0 * cm, 2.2 * cm, 2.8 * cm, 3.5 * cm, 2.3 * cm],
                header_color="#7F1D1D",
            ))
    else:
        story.append(Paragraph("No se ha cargado un archivo ISR-Live filtrado en la sesion actual.", styles["FindingText"]))

    # Plan de acciones abiertas
    story.append(PageBreak())
    story.append(Paragraph("Plan de accion y pendientes", styles["SectionHeader"]))
    open_plan = assessment[assessment["Status"].isin(["Open", "In progress", "Overdue"])].copy()
    if open_plan.empty:
        story.append(Paragraph("No hay acciones abiertas registradas en el assessment actual.", styles["FindingText"]))
    else:
        story.append(dataframe_to_pdf_table(
            open_plan,
            ["ID", "Category", "Question", "Risk", "Status", "Owner", "Due date", "Action plan"],
            styles,
            max_rows=100,
            widths=[1.3 * cm, 3.0 * cm, 3.4 * cm, 1.7 * cm, 2.0 * cm, 2.3 * cm, 1.9 * cm, 4.2 * cm],
            header_color="#92400E",
        ))

    story.append(Spacer(1, 0.35 * cm))
    story.append(Paragraph("Nota tecnica: este informe consolida la informacion diligenciada en la app, la evidencia cargada durante la sesion y los datos ISR-Live cargados para el distribuidor seleccionado. La interpretacion final debe validarse contra los procedimientos corporativos vigentes y la evidencia original.", styles["TinyText"]))

    doc.build(story)
    return buffer.getvalue()

def page_export_all(distributor: str, country: str, start_date: date, end_date: date) -> None:
    st.subheader("Exportación consolidada")
    assessment = build_assessment_dataframe()
    isr = st.session_state.get("last_isrlive_std", pd.DataFrame())
    meta = pd.DataFrame([{
        "Distributor": distributor,
        "Country": country,
        "Period start": str(start_date),
        "Period end": str(end_date),
        "Generated at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Build": APP_VERSION,
    }])
    sheets = {"Summary": meta, "Corporate Assessment": assessment}
    if isinstance(isr, pd.DataFrame) and not isr.empty:
        sheets["ISR-Live Analysis"] = isr
        sheets["Machine Config Issues"] = isr[isr["Machine Config Status"] == "Incomplete / invalid"]

    excel_bytes = to_excel_bytes(sheets)
    st.download_button(
        "Descargar paquete consolidado Excel",
        data=excel_bytes,
        file_name=f"LATAM_Service_Assessment_{distributor}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx".replace(" ", "_"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    json_payload = {
        "metadata": meta.to_dict(orient="records"),
        "assessment": assessment.to_dict(orient="records"),
        "isrlive": isr.to_dict(orient="records") if isinstance(isr, pd.DataFrame) and not isr.empty else [],
    }
    st.download_button(
        "Descargar respaldo JSON",
        data=json.dumps(json_payload, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=f"LATAM_Service_Assessment_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
    )

    st.markdown("### Informe PDF tecnico")
    st.caption("Genera un PDF con normas tecnicas, score, resultados del assessment, evidencias cargadas, analisis ISR-Live y plan de accion.")
    if REPORTLAB_AVAILABLE:
        try:
            pdf_bytes = create_technical_pdf_report(distributor, country, start_date, end_date)
            st.download_button(
                "Descargar informe PDF tecnico",
                data=pdf_bytes,
                file_name=f"Technical_Assessment_Report_{distributor}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf".replace(" ", "_"),
                mime="application/pdf",
            )
        except Exception as exc:
            st.error(f"No fue posible generar el PDF: {exc}")
    else:
        st.error("ReportLab no esta instalado. Verifica que requirements.txt incluya reportlab.")


def render_global_pdf_download_panel(distributor: str, country: str, start_date: date, end_date: date) -> None:
    st.markdown(
        """
        <div class="pdf-panel">
            <div class="pdf-panel-title">📄 Informe técnico normativo disponible</div>
            <div class="pdf-panel-subtitle">Descarga un PDF consolidado con referencias técnicas internacionales, resultados del assessment, evidencias cargadas, análisis ISR-Live y plan de acción.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if REPORTLAB_AVAILABLE:
        try:
            pdf_bytes = create_technical_pdf_report(distributor, country, start_date, end_date)
            st.download_button(
                "📄 Descargar PDF con normas técnicas internacionales",
                data=pdf_bytes,
                file_name=f"Technical_Normative_Assessment_Report_{distributor}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf".replace(" ", "_"),
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key="global_pdf_download",
            )
        except Exception as exc:
            st.error(f"No fue posible generar el PDF técnico normativo: {exc}")
    else:
        st.error("No se puede generar el PDF porque ReportLab no está instalado. Verifica que requirements.txt incluya reportlab y redeploya la app.")



# ============================================================
# Main
# ============================================================

def main() -> None:
    st.set_page_config(page_title="LATAM Service Assessment", page_icon="🧪", layout="wide")
    inject_css()
    distributor, country, start_date, end_date, pdf_container = sidebar_context()
    render_header()

    page_corporate_assessment(distributor, country, start_date, end_date)
    st.markdown("---")
    page_isrlive(distributor, country)

    # El generador de PDF queda en la barra lateral izquierda, debajo del contexto del assessment
    render_sidebar_pdf_panel(pdf_container, distributor, country, start_date, end_date)


if __name__ == "__main__":
    main()
