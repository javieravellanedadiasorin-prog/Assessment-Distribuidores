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
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# Configuración base
# ============================================================

APP_VERSION = "v3.5 - Emergency Stable Build"
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
            <p>Assessment corporativo completo con evidencia por pregunta + análisis ISR-Live enfocado únicamente en el distribuidor seleccionado.</p>
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


# ============================================================
# Sidebar
# ============================================================

def sidebar_context() -> Tuple[str, str, date, date]:
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

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Build activo: {APP_VERSION}")
    st.session_state["selected_distributor"] = selected_distributor
    st.session_state["selected_country"] = selected_country
    st.session_state["period_start"] = str(start_date)
    st.session_state["period_end"] = str(end_date)
    return selected_distributor, selected_country, start_date, end_date


# ============================================================
# Páginas
# ============================================================

def page_corporate_assessment(distributor: str, country: str, start_date: date, end_date: date) -> None:
    st.subheader("Assessment corporativo completo")
    st.caption("Todas las preguntas del formato original aparecen aquí como tarjetas editables, con evidencia independiente por cada punto.")

    df_assessment = build_assessment_dataframe()
    valid_scores = df_assessment["Score"].dropna()
    global_score = round(valid_scores.mean() * 100, 1) if len(valid_scores) else 0
    completed = int(df_assessment["Response"].str.startswith(("Y", "P", "N"), na=False).sum())
    evidence_count = sum(len(get_question_state(q["id"]).get("files", [])) for q in CORPORATE_QUESTIONS)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score corporativo", f"{global_score}%")
    c2.metric("Preguntas respondidas", f"{completed}/{len(CORPORATE_QUESTIONS)}")
    c3.metric("Evidencias cargadas", evidence_count)
    c4.metric("Distribuidor", distributor)

    categories = list(dict.fromkeys(q["category"] for q in CORPORATE_QUESTIONS))
    category_filter = st.multiselect("Filtrar categorías", categories, default=categories)

    for category in categories:
        if category not in category_filter:
            continue
        st.markdown(f"<h3 class='section-title'>{category}</h3>", unsafe_allow_html=True)
        for q in [x for x in CORPORATE_QUESTIONS if x["category"] == category]:
            render_question_card(q)

    df_assessment = build_assessment_dataframe()
    category_score = (
        df_assessment.dropna(subset=["Score"])
        .groupby("Category", as_index=False)["Score"].mean()
    )
    if not category_score.empty:
        category_score["Score %"] = (category_score["Score"] * 100).round(1)
        st.markdown("### Score por categoría")
        fig = px.bar(category_score, x="Category", y="Score %", text="Score %", title="Corporate assessment score by category")
        fig.update_layout(height=430, xaxis_title="Categoría", yaxis_title="Score %")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Exportar assessment")
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
    fig1 = px.bar(by_model, x="Instrument Model", y="Installed Base", text="Installed Base", title="Installed Base by Instrument Model")
    fig1.update_layout(height=420, xaxis_title="Modelo", yaxis_title="Cantidad")
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("### Machine Configuration por modelo")
    mc = std.groupby(["Instrument Model", "Machine Config Status"], as_index=False).size().rename(columns={"size": "Count"})
    fig2 = px.bar(mc, x="Instrument Model", y="Count", color="Machine Config Status", text="Count", barmode="group", title="Machine Configuration complete vs incomplete by model")
    fig2.update_layout(height=430, xaxis_title="Modelo", yaxis_title="Cantidad")
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("### Instrument Status por modelo")
    st_df = std.groupby(["Instrument Model", "Instrument Status"], as_index=False).size().rename(columns={"size": "Count"})
    fig3 = px.bar(st_df, x="Instrument Model", y="Count", color="Instrument Status", text="Count", barmode="stack", title="Instrument Status by model")
    fig3.update_layout(height=470, xaxis_title="Modelo", yaxis_title="Cantidad")
    st.plotly_chart(fig3, use_container_width=True)


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


# ============================================================
# Main
# ============================================================

def main() -> None:
    st.set_page_config(page_title="LATAM Service Assessment", page_icon="🧪", layout="wide")
    inject_css()
    distributor, country, start_date, end_date = sidebar_context()
    render_header()

    page = st.tabs([
        "Assessment corporativo",
        "Análisis ISR-Live",
        "Exportación consolidada",
    ])

    with page[0]:
        page_corporate_assessment(distributor, country, start_date, end_date)
    with page[1]:
        page_isrlive(distributor, country)
    with page[2]:
        page_export_all(distributor, country, start_date, end_date)


if __name__ == "__main__":
    main()
