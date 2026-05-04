# ============================================================
# LATAM Distributor Service Excellence Assessment
# Version 3.3 - Corporate Assessment Cards + ISR-Live Focus
# ============================================================

from __future__ import annotations

import base64
import io
import json
import os
import re
import sqlite3
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
    REPORTLAB_OK = True
except Exception:
    REPORTLAB_OK = False

# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------
BASE_DIR = Path(__file__).parent if "__file__" in globals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
EVIDENCE_DIR = BASE_DIR / "evidence"
OUTPUT_DIR = BASE_DIR / "outputs"
DB_PATH = DATA_DIR / "assessment_app.db"
DATA_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

CORPORATE_QUESTIONS_PATH = DATA_DIR / "corporate_assessment_questions.csv"
DISTRIBUTORS_LATAM_PATH = DATA_DIR / "distributors_master_latam.csv"
DISTRIBUTORS_MASTER_PATH = DATA_DIR / "distributors_master.csv"

APP_TITLE = "LATAM Distributor Service Excellence Assessment"
APP_VERSION = "v3.3"

RESPONSE_SCORE = {
    "Y - Cumple": 1.0,
    "P - Parcial": 0.5,
    "N - No cumple": 0.0,
    "NA - No aplica": np.nan,
}

RISK_ORDER = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}

CATEGORY_WEIGHTS = {
    "Installed Base Certification": 0.20,
    "Contact List": 0.10,
    "DiaSorin Accounts Optimization": 0.10,
    "Technical Evaluation": 0.15,
    "Service Tools": 0.15,
    "Stock Level": 0.10,
    "Service Traceability System": 0.10,
    "Customer Visit": 0.10,
}

INVALID_MC_VALUES = {
    "", "-", "--", "n/a", "na", "nan", "none", "null", "no disponible",
    "data not available", "data no available", "data no disponible", "not available",
    "dont know", "don't know", "do not know", "unknown", "not done", "no hecho",
    "sin informacion", "sin información", "pending", "pendiente", "tbc", "to be checked",
}

COLUMN_SYNONYMS = {
    "distributor": ["Distributor name", "Distributor", "Dealer", "Partner", "Distribuidor"],
    "country": ["Country", "Pais", "País"],
    "instrument_type": ["Instrument type", "Instrument Type", "Model", "Analyzer", "Instrument", "Tipo de instrumento"],
    "serial_number": ["Serial number", "Serial Number", "SN", "S/N", "Serial", "Número de serie", "Numero de serie"],
    "customer_name": ["Customer name", "Customer", "Client", "Cliente", "Nombre cliente"],
    "city": ["City", "Ciudad"],
    "machine_config": ["Machine Configurations", "Machine Configuration", "Machine config", "Configuration", "Configuración", "Configuracion"],
    "instrument_status": [" Instrument Status", "Instrument Status", "Status", " Estado", "Estado", "Instrument status"],
    "software_version": ["Software version", "Software Version", "User SW", "User Software", "SW Version", "Version", "Versión software"],
    "os_version": ["Operating System", "OS", "OS Version", "Windows version", "Windows Version", "Sistema operativo"],
    "blood_bank": ["In Blook Bank", "In Blood Bank", "Blood Bank", "Banco de sangre", "Banco Sangre"],
}

# ------------------------------------------------------------
# CSS / UI
# ------------------------------------------------------------
def inject_css() -> None:
    st.markdown(
        """
        <style>
        .main .block-container {max-width: 1520px; padding-top: 1.1rem; padding-bottom: 2rem;}
        div[data-testid="stMetric"] {
            background: linear-gradient(135deg, rgba(15,23,42,.92), rgba(8,47,73,.62));
            border: 1px solid rgba(34,211,238,.22);
            padding: 14px 16px;
            border-radius: 18px;
            box-shadow: 0 12px 30px rgba(0,0,0,.18);
        }
        div[data-testid="stMetricValue"] {font-size: 1.65rem; color: #E0F2FE;}
        .hero {
            padding: 1.35rem 1.6rem;
            border-radius: 24px;
            background:
                radial-gradient(circle at 12% 20%, rgba(0,229,255,.22), transparent 26%),
                radial-gradient(circle at 82% 0%, rgba(99,102,241,.25), transparent 30%),
                linear-gradient(135deg, #020617 0%, #0f172a 48%, #062B3C 100%);
            border: 1px solid rgba(125,211,252,.28);
            box-shadow: 0 16px 45px rgba(0,0,0,.32);
            margin-bottom: 1rem;
        }
        .hero h1 {margin:0; font-size: 1.9rem; letter-spacing:.2px; color:#F8FAFC;}
        .hero p {margin:.35rem 0 0 0; color:#BAE6FD; font-size:.98rem;}
        .tag {
            display:inline-block; padding:.22rem .58rem; border-radius:999px;
            border:1px solid rgba(34,211,238,.4); color:#A5F3FC; background:rgba(8,47,73,.35);
            margin-right:.4rem; font-size:.78rem;
        }
        .section-title {
            font-size: 1.25rem; font-weight: 800; color:#F8FAFC; margin: 1.1rem 0 .55rem 0;
        }
        .category-band {
            margin-top: 1.1rem; padding: .9rem 1rem; border-radius: 18px;
            background: linear-gradient(90deg, rgba(14,165,233,.24), rgba(15,23,42,.5));
            border: 1px solid rgba(125,211,252,.22);
            font-weight: 800; color: #E0F2FE; font-size: 1.05rem;
        }
        .assessment-card {
            border:1px solid rgba(148,163,184,.22);
            border-left: 4px solid #22D3EE;
            background: linear-gradient(135deg, rgba(15,23,42,.88), rgba(2,6,23,.88));
            padding: 1rem 1.05rem;
            border-radius: 20px;
            margin-bottom: .85rem;
            box-shadow: 0 10px 26px rgba(0,0,0,.22);
        }
        .assessment-card h4 {margin:0 0 .35rem 0; color:#F8FAFC; font-size:1.05rem;}
        .assessment-card .definition {color:#CBD5E1; font-size:.91rem; line-height:1.35rem; white-space:pre-wrap;}
        .assessment-card .needed {color:#FDE68A; font-size:.86rem; line-height:1.25rem; white-space:pre-wrap;}
        .evidence-pill {
            display:inline-block; background:rgba(34,197,94,.16); color:#BBF7D0;
            border:1px solid rgba(34,197,94,.35); padding:.18rem .5rem; border-radius:999px; font-size:.78rem;
        }
        .warning-pill {
            display:inline-block; background:rgba(245,158,11,.14); color:#FDE68A;
            border:1px solid rgba(245,158,11,.32); padding:.18rem .5rem; border-radius:999px; font-size:.78rem;
        }
        .bad-pill {
            display:inline-block; background:rgba(239,68,68,.14); color:#FECACA;
            border:1px solid rgba(239,68,68,.32); padding:.18rem .5rem; border-radius:999px; font-size:.78rem;
        }
        .small-muted {color:#94A3B8; font-size:.85rem;}
        .stTabs [data-baseweb="tab-list"] {gap: 8px;}
        .stTabs [data-baseweb="tab"] {
            background: rgba(15,23,42,.72); border-radius: 14px; padding: 8px 14px;
            border: 1px solid rgba(148,163,184,.18);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        f"""
        <div class="hero">
            <span class="tag">DiaSorin LATAM</span><span class="tag">Technical Support Health Check</span><span class="tag">{APP_VERSION}</span>
            <h1>{APP_TITLE}</h1>
            <p>Assessment corporativo con evidencia por pregunta + análisis ISR-Live enfocado únicamente en el distribuidor seleccionado.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def safe_filename(value: str) -> str:
    value = str(value or "").strip()
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:140] or "file"


def normalize_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text)


def normalize_key(value) -> str:
    text = normalize_text(value).lower()
    text = text.replace("’", "'").replace("´", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def canonical_col_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


def get_col(df: pd.DataFrame, logical_name: str) -> Optional[str]:
    normalized = {canonical_col_name(c): c for c in df.columns}
    for candidate in COLUMN_SYNONYMS.get(logical_name, []):
        key = canonical_col_name(candidate)
        if key in normalized:
            return normalized[key]
    # flexible fallback
    tokens = {
        "distributor": ["distributor"],
        "country": ["country"],
        "instrument_type": ["instrument", "type"],
        "serial_number": ["serial"],
        "customer_name": ["customer"],
        "machine_config": ["machine", "config"],
        "instrument_status": ["status"],
    }.get(logical_name, [])
    for col in df.columns:
        low = str(col).lower()
        if tokens and all(t in low for t in tokens):
            return col
    return None


def clean_instrument_type(value: str) -> str:
    text = normalize_text(value)
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    low = text.lower()
    if "xl las" in low:
        return "LIAISON XL LAS"
    if "liaison xl" in low or low in {"xl", "lxl"}:
        return "LIAISON XL"
    if "liaison xs" in low or low in {"xs", "lxs"}:
        return "LIAISON XS"
    if "liaison" in low:
        return "LIAISON"
    return text or "Not reported"


def is_invalid_machine_config(value: str) -> bool:
    low = normalize_key(value)
    if low in INVALID_MC_VALUES:
        return True
    if len(low) < 3:
        return True
    return False


def read_table(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    data = bytes(uploaded_file.getbuffer())
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(data), dtype=str)
    # CSV: delimiter/encoding robusto
    for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
        try:
            text = data.decode(enc)
        except Exception:
            continue
        sample = text[:6000]
        sep = ";" if sample.count(";") > sample.count(",") else ","
        try:
            return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, engine="python", on_bad_lines="skip", index_col=False)
        except Exception:
            try:
                return pd.read_csv(io.StringIO(text), sep=None, dtype=str, engine="python", on_bad_lines="skip", index_col=False)
            except Exception:
                pass
    raise ValueError("No fue posible leer el archivo cargado.")

# ------------------------------------------------------------
# Data loading
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_distributors() -> pd.DataFrame:
    path = DISTRIBUTORS_LATAM_PATH if DISTRIBUTORS_LATAM_PATH.exists() else DISTRIBUTORS_MASTER_PATH
    if not path.exists():
        return pd.DataFrame(columns=["Distributor name", "Country", "World Region", "Commercial Region"])
    df = pd.read_csv(path, dtype=str).fillna("")
    required = ["Distributor name", "Country", "World Region", "Commercial Region"]
    for c in required:
        if c not in df.columns:
            df[c] = ""
    for c in required:
        df[c] = df[c].astype(str).str.strip()
    df = df[df["Distributor name"].ne("")].drop_duplicates()
    return df.sort_values(["Distributor name", "Country"])


FALLBACK_QUESTIONS = [
    ["Customer Visit", "Customer 1", "Visit a customer where the PM has been performed in the instrument in the last 3 months (LXL)", "", "Y", "Fundacion Santa Fe de Bogotá LXL/LAS 2210100729"],
    ["Customer Visit", "Customer 2", "VIP customer visit.", "", "P", "Herasmo Meoz Cucuta LXL 2210007457-2210007453"],
    ["Customer Visit", "Customer 3", "System with the most amount of failures.", "", "P", "Higuera Escalante Bucaramanga LXS 2290000331"],
    ["Service Tools", "Lubrication Kits", "How many kits are available in the stock?\nHow many FSEs are in possession of a full kit? (Lubrication Kit and Super lube).\nDefine the amount of kits to be ordered.", "Data to be compiled before the assessment:\n# of fits available in stock.\n# of kits already provided to FSEs.", "Y", "3 kits in stock, 4 Superlub kits, 5 engineers with kits in their tool case, no need to order"],
]

@st.cache_data(show_spinner=False)
def load_corporate_questions() -> pd.DataFrame:
    if CORPORATE_QUESTIONS_PATH.exists():
        df = pd.read_csv(CORPORATE_QUESTIONS_PATH, dtype=str).fillna("")
    else:
        df = pd.DataFrame(FALLBACK_QUESTIONS, columns=["Macro Category", "Item", "Definition", "Needed In Advance", "Original Response", "Original Comments"])
    # standard columns
    expected = ["Macro Category", "Item", "Definition", "Needed In Advance", "Original Response", "Original Comments", "Evidence Required"]
    for c in expected:
        if c not in df.columns:
            df[c] = ""
    # sort by intended corporate order
    cat_order = {cat: i for i, cat in enumerate(CATEGORY_WEIGHTS.keys())}
    df["__order"] = df["Macro Category"].map(cat_order).fillna(999)
    df = df.sort_values(["__order", "Macro Category", "Item"]).drop(columns=["__order"])
    df = df.reset_index(drop=True)
    df["Question ID"] = [f"Q{idx+1:02d}" for idx in range(len(df))]
    return df

# ------------------------------------------------------------
# State / scoring
# ------------------------------------------------------------
def init_question_state(questions: pd.DataFrame) -> None:
    if "assessment_state_ready" not in st.session_state:
        st.session_state["assessment_state_ready"] = True
    for _, row in questions.iterrows():
        qid = row["Question ID"]
        original = normalize_text(row.get("Original Response", ""))
        default_response = {"Y": "Y - Cumple", "P": "P - Parcial", "N": "N - No cumple"}.get(original.upper(), "P - Parcial")
        defaults = {
            f"resp_{qid}": default_response,
            f"risk_{qid}": "Medium" if default_response == "P - Parcial" else ("Low" if default_response == "Y - Cumple" else "High"),
            f"status_{qid}": "Closed" if default_response == "Y - Cumple" else "Open",
            f"owner_{qid}": "Distributor / DiaSorin",
            f"due_{qid}": date.today(),
            f"comments_{qid}": normalize_text(row.get("Original Comments", "")),
            f"action_{qid}": "",
            f"evidence_notes_{qid}": "",
            f"evidence_files_{qid}": [],
        }
        for key, val in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = val


def question_snapshot(questions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in questions.iterrows():
        qid = row["Question ID"]
        resp = st.session_state.get(f"resp_{qid}", "P - Parcial")
        score = RESPONSE_SCORE.get(resp, 0.0)
        rows.append({
            "Question ID": qid,
            "Macro Category": row["Macro Category"],
            "Item": row["Item"],
            "Definition": row["Definition"],
            "Needed In Advance": row.get("Needed In Advance", ""),
            "Evidence Required": row.get("Evidence Required", ""),
            "Response": resp,
            "Score": score,
            "Risk": st.session_state.get(f"risk_{qid}", "Medium"),
            "Item Status": st.session_state.get(f"status_{qid}", "Open"),
            "Responsible": st.session_state.get(f"owner_{qid}", ""),
            "Due Date": str(st.session_state.get(f"due_{qid}", "")),
            "Comments / Notes": st.session_state.get(f"comments_{qid}", ""),
            "Action Plan": st.session_state.get(f"action_{qid}", ""),
            "Evidence Notes": st.session_state.get(f"evidence_notes_{qid}", ""),
            "Evidence Files": "; ".join(st.session_state.get(f"evidence_files_{qid}", [])),
            "Evidence Uploaded": "Yes" if st.session_state.get(f"evidence_files_{qid}", []) else "No",
        })
    return pd.DataFrame(rows)


def calculate_summary(snapshot: pd.DataFrame) -> Dict:
    if snapshot.empty:
        return {"overall": 0, "open": 0, "critical": 0, "by_category": pd.DataFrame()}
    valid = snapshot[~snapshot["Score"].isna()].copy()
    by_cat_rows = []
    weighted_total = 0.0
    weight_sum = 0.0
    for cat, group in valid.groupby("Macro Category", dropna=False):
        cat_score = float(group["Score"].mean() * 100) if len(group) else 0.0
        weight = CATEGORY_WEIGHTS.get(cat, 0.05)
        weighted_total += cat_score * weight
        weight_sum += weight
        by_cat_rows.append({
            "Macro Category": cat,
            "Score": round(cat_score, 1),
            "Items": int(len(group)),
            "Open/Partial": int(group["Response"].isin(["P - Parcial", "N - No cumple"]).sum()),
            "Weight": weight,
        })
    overall = round(weighted_total / weight_sum, 1) if weight_sum else round(float(valid["Score"].mean() * 100), 1)
    maturity = "Best in class" if overall >= 95 else "Maduro" if overall >= 90 else "Controlado" if overall >= 80 else "En desarrollo" if overall >= 65 else "Crítico"
    return {
        "overall": overall,
        "maturity": maturity,
        "open": int(snapshot["Response"].isin(["P - Parcial", "N - No cumple"]).sum()),
        "critical": int((snapshot["Risk"] == "Critical").sum()),
        "evidence": int((snapshot["Evidence Uploaded"] == "Yes").sum()),
        "total_questions": int(len(snapshot)),
        "by_category": pd.DataFrame(by_cat_rows).sort_values("Score") if by_cat_rows else pd.DataFrame(),
    }


def save_uploaded_evidence(distributor: str, period: str, qid: str, category: str, item: str, files: List, notes: str) -> List[str]:
    if not files:
        return []
    folder = EVIDENCE_DIR / safe_filename(distributor) / safe_filename(period) / safe_filename(qid + "_" + category) / safe_filename(item)
    folder.mkdir(parents=True, exist_ok=True)
    stored_names = []
    for f in files:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = folder / f"{timestamp}_{safe_filename(f.name)}"
        with open(dest, "wb") as out:
            out.write(bytes(f.getbuffer()))
        stored_names.append(f.name)
    if notes:
        with open(folder / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_notes.txt", "w", encoding="utf-8") as out:
            out.write(notes)
    return stored_names

# ------------------------------------------------------------
# Distributor selector
# ------------------------------------------------------------
def distributor_selector() -> Dict:
    dist_df = load_distributors()
    if dist_df.empty:
        st.sidebar.error("No encontré data/distributors_master_latam.csv ni data/distributors_master.csv")
        return {"distributor": "", "country": "", "world_region": "", "commercial_region": "", "period": ""}

    distributors = sorted(dist_df["Distributor name"].dropna().unique().tolist())
    if "selected_distributor" not in st.session_state:
        st.session_state["selected_distributor"] = distributors[0] if distributors else ""

    st.sidebar.markdown("### Evaluación")
    distributor = st.sidebar.selectbox("Distribuidor", distributors, key="selected_distributor")
    rows = dist_df[dist_df["Distributor name"] == distributor].copy()
    countries = sorted(rows["Country"].dropna().unique().tolist()) or [""]
    country = st.sidebar.selectbox("País", countries, key="selected_country")

    region_row = rows[rows["Country"] == country].head(1)
    if region_row.empty:
        region_row = rows.head(1)
    world_region = normalize_text(region_row.iloc[0].get("World Region", "")) if not region_row.empty else ""
    commercial_region = normalize_text(region_row.iloc[0].get("Commercial Region", "")) if not region_row.empty else ""

    st.sidebar.text_input("World Region", value=world_region, disabled=True)
    st.sidebar.text_input("Commercial Region", value=commercial_region, disabled=True)

    st.sidebar.markdown("### Periodo")
    period_start = st.sidebar.date_input("Fecha inicial", value=date(date.today().year, 1, 1), key="period_start")
    period_end = st.sidebar.date_input("Fecha final", value=date.today(), key="period_end")
    if period_start > period_end:
        st.sidebar.warning("La fecha inicial no puede ser mayor que la fecha final.")
    period = f"{period_start.isoformat()} to {period_end.isoformat()}"
    return {
        "distributor": distributor,
        "country": country,
        "world_region": world_region,
        "commercial_region": commercial_region,
        "period_start": period_start,
        "period_end": period_end,
        "period": period,
    }

# ------------------------------------------------------------
# Corporate Assessment Page
# ------------------------------------------------------------
def response_badge(resp: str) -> str:
    if resp == "Y - Cumple":
        return '<span class="evidence-pill">Cumple</span>'
    if resp == "P - Parcial":
        return '<span class="warning-pill">Parcial</span>'
    if resp == "N - No cumple":
        return '<span class="bad-pill">No cumple</span>'
    return '<span class="small-muted">No aplica</span>'


def page_corporate(meta: Dict) -> None:
    questions = load_corporate_questions()
    init_question_state(questions)
    snapshot = question_snapshot(questions)
    summary = calculate_summary(snapshot)

    st.markdown('<div class="section-title">Assessment corporativo completo</div>', unsafe_allow_html=True)
    st.caption("Aquí deben verse todas las preguntas del formato original. Cada pregunta tiene su propio espacio para respuesta, riesgo, plan de acción y evidencia.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preguntas", summary["total_questions"])
    c2.metric("Score", f"{summary['overall']}%")
    c3.metric("Madurez", summary["maturity"])
    c4.metric("Abiertas/parciales", summary["open"])
    c5.metric("Evidencias", f"{summary['evidence']}/{summary['total_questions']}")

    by_cat = summary["by_category"]
    if not by_cat.empty:
        fig = px.bar(by_cat, x="Macro Category", y="Score", text="Score", hover_data=["Items", "Open/Partial"], title="Score por categoría corporativa")
        fig.update_layout(height=360, xaxis_title="", yaxis_title="Score", margin=dict(l=20, r=20, t=60, b=80))
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Datos generales de la evaluación", expanded=True):
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.text_input("Distribuidor", value=meta["distributor"], disabled=True)
        cc2.text_input("País", value=meta["country"], disabled=True)
        cc3.text_input("Periodo", value=meta["period"], disabled=True)
        reviewer = cc4.text_input("Reviewer", value=st.session_state.get("reviewer", "Javier Avellaneda"), key="reviewer")
        general_notes = st.text_area("Notas generales", value=st.session_state.get("general_notes", ""), key="general_notes", height=90)

    # Global reset/download controls
    top1, top2, top3 = st.columns([1, 1, 2])
    if top1.button("Recargar respuestas base", use_container_width=True):
        for key in list(st.session_state.keys()):
            if re.match(r"^(resp|risk|status|owner|due|comments|action|evidence_notes|evidence_files)_Q\d+", key):
                del st.session_state[key]
        st.session_state.pop("assessment_state_ready", None)
        st.rerun()
    if top2.button("Marcar todo en revisión", use_container_width=True):
        for qid in questions["Question ID"]:
            st.session_state[f"status_{qid}"] = "In Progress"
        st.rerun()

    # Cards by category
    for category, group in questions.groupby("Macro Category", sort=False):
        st.markdown(f'<div class="category-band">{category} · {len(group)} puntos</div>', unsafe_allow_html=True)
        for _, q in group.iterrows():
            qid = q["Question ID"]
            st.markdown(
                f"""
                <div class="assessment-card">
                    <h4>{qid} · {q['Item']} {response_badge(st.session_state.get(f'resp_{qid}', 'P - Parcial'))}</h4>
                    <div class="definition"><b>Definición:</b><br>{q['Definition']}</div>
                    {f'<br><div class="needed"><b>Needed in advance:</b><br>{q.get("Needed In Advance", "")}</div>' if normalize_text(q.get('Needed In Advance','')) else ''}
                    {f'<br><div class="small-muted"><b>Evidencia esperada:</b> {q.get("Evidence Required", "")}</div>' if normalize_text(q.get('Evidence Required','')) else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )
            w1, w2, w3, w4, w5 = st.columns([1.15, 1, 1, 1, 1])
            with w1:
                st.selectbox("Respuesta", list(RESPONSE_SCORE.keys()), key=f"resp_{qid}", label_visibility="collapsed")
            with w2:
                st.selectbox("Riesgo", ["Low", "Medium", "High", "Critical"], key=f"risk_{qid}", label_visibility="collapsed")
            with w3:
                st.selectbox("Estado", ["Open", "In Progress", "Closed", "Overdue", "Not Applicable"], key=f"status_{qid}", label_visibility="collapsed")
            with w4:
                st.text_input("Responsable", key=f"owner_{qid}", label_visibility="collapsed")
            with w5:
                st.date_input("Fecha compromiso", key=f"due_{qid}", label_visibility="collapsed")

            cnotes, caction = st.columns(2)
            with cnotes:
                st.text_area("Comentarios / notas", key=f"comments_{qid}", height=82)
            with caction:
                st.text_area("Plan de acción", key=f"action_{qid}", height=82)

            enotes, eupload = st.columns([1, 1.4])
            with enotes:
                st.text_area("Nota de evidencia", key=f"evidence_notes_{qid}", height=72)
            with eupload:
                uploaded_files = st.file_uploader(
                    f"Evidencia para {qid} - {q['Item']}",
                    type=["png", "jpg", "jpeg", "pdf", "xlsx", "xls", "csv", "txt", "zip", "docx", "pptx"],
                    accept_multiple_files=True,
                    key=f"upload_{qid}",
                )
                colsave, colstatus = st.columns([.8, 1.2])
                with colsave:
                    if st.button("Guardar evidencia", key=f"save_ev_{qid}", use_container_width=True):
                        stored = save_uploaded_evidence(
                            meta["distributor"], meta["period"], qid, q["Macro Category"], q["Item"], uploaded_files,
                            st.session_state.get(f"evidence_notes_{qid}", ""),
                        )
                        if stored:
                            existing = list(st.session_state.get(f"evidence_files_{qid}", []))
                            st.session_state[f"evidence_files_{qid}"] = existing + stored
                            st.success(f"Evidencia guardada para {qid}.")
                        else:
                            st.warning("Carga al menos un archivo antes de guardar.")
                with colstatus:
                    files = st.session_state.get(f"evidence_files_{qid}", [])
                    if files:
                        st.markdown(f'<span class="evidence-pill">{len(files)} archivo(s): {", ".join(files[:3])}</span>', unsafe_allow_html=True)
                    else:
                        st.markdown('<span class="warning-pill">Sin evidencia cargada</span>', unsafe_allow_html=True)
            st.divider()

    # Exports
    snapshot = question_snapshot(questions)
    summary = calculate_summary(snapshot)
    st.markdown('<div class="section-title">Exportar informe</div>', unsafe_allow_html=True)
    xlsx = build_excel_report(snapshot, summary, meta, reviewer, general_notes)
    colx, colp, colj = st.columns(3)
    with colx:
        st.download_button(
            "Descargar informe Excel",
            data=xlsx,
            file_name=f"Service_Assessment_{safe_filename(meta['distributor'])}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with colp:
        if REPORTLAB_OK:
            pdf = build_pdf_report(snapshot, summary, meta, reviewer, general_notes)
            st.download_button(
                "Descargar informe PDF",
                data=pdf,
                file_name=f"Service_Assessment_{safe_filename(meta['distributor'])}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.info("PDF no disponible: falta reportlab.")
    with colj:
        payload = {"meta": {**meta, "reviewer": reviewer, "notes": general_notes}, "items": snapshot.to_dict(orient="records")}
        st.download_button(
            "Descargar respaldo JSON",
            data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"Service_Assessment_Backup_{safe_filename(meta['distributor'])}.json",
            mime="application/json",
            use_container_width=True,
        )

# ------------------------------------------------------------
# ISR-Live Analysis
# ------------------------------------------------------------
def standardize_isrlive(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    for logical in COLUMN_SYNONYMS:
        col = get_col(df, logical)
        out[logical] = df[col].apply(normalize_text) if col else ""
    out["instrument_type"] = out["instrument_type"].apply(clean_instrument_type)
    out["serial_number"] = out["serial_number"].str.replace(r"\.0$", "", regex=True)
    out["machine_config_ok"] = ~out["machine_config"].apply(is_invalid_machine_config)
    out["machine_config_status"] = np.where(out["machine_config_ok"], "Completa", "Incompleta / inválida")
    out["instrument_status_clean"] = out["instrument_status"].replace("", "Status not reported")
    out["blood_bank"] = out["blood_bank"].replace("", "Not reported")
    return out


def filter_by_distributor(df: pd.DataFrame, selected_distributor: str, selected_country: str) -> pd.DataFrame:
    if df.empty:
        return df
    target = normalize_key(selected_distributor)
    target_country = normalize_key(selected_country)
    dist_key = df["distributor"].apply(normalize_key)
    mask = dist_key.eq(target)
    if mask.sum() == 0:
        # fallback contains both directions, useful if ISR-Live uses short/long legal names
        mask = dist_key.apply(lambda x: target in x or x in target if x else False)
    # country helps when duplicate distributor name exists, but do not remove valid rows if country missing
    if selected_country and "country" in df.columns:
        country_key = df["country"].apply(normalize_key)
        country_mask = country_key.eq(target_country)
        if (mask & country_mask).sum() > 0:
            mask = mask & country_mask
    return df[mask].copy()


def page_isrlive(meta: Dict) -> None:
    st.markdown('<div class="section-title">Análisis ISR-Live por distribuidor</div>', unsafe_allow_html=True)
    st.caption("Este análisis se filtra únicamente por el distribuidor seleccionado en la barra lateral. Las gráficas muestran base instalada, Machine Configuration y status por modelo.")

    uploaded = st.file_uploader("Subir CSV/XLSX exportado de ISR-Live", type=["csv", "xlsx", "xls"], key="isrlive_upload")
    if not uploaded:
        st.info("Carga el archivo de ISR-Live para iniciar el análisis.")
        return

    try:
        raw = read_table(uploaded)
        std = standardize_isrlive(raw)
    except Exception as exc:
        st.error(f"No pude leer/normalizar el archivo: {exc}")
        return

    filtered = filter_by_distributor(std, meta["distributor"], meta["country"])
    if filtered.empty:
        st.error("No encontré registros para el distribuidor seleccionado dentro del archivo ISR-Live cargado.")
        detected = std[["distributor", "country"]].drop_duplicates().sort_values(["distributor", "country"]).head(100)
        st.markdown("Distribuidores detectados en el archivo:")
        st.dataframe(detected, use_container_width=True, hide_index=True)
        return

    total = len(filtered)
    mc_ok = int(filtered["machine_config_ok"].sum())
    mc_bad = int(total - mc_ok)
    models = int(filtered["instrument_type"].nunique())
    statuses = int(filtered["instrument_status_clean"].nunique())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Base instalada filtrada", total)
    c2.metric("Modelos", models)
    c3.metric("Machine Config OK", mc_ok)
    c4.metric("Machine Config pendiente", mc_bad)

    # Charts specifically requested
    base_model = filtered.groupby("instrument_type", dropna=False).size().reset_index(name="Cantidad").sort_values("Cantidad", ascending=False)
    fig1 = px.bar(base_model, x="instrument_type", y="Cantidad", text="Cantidad", title="Base instalada por modelo")
    fig1.update_layout(height=380, xaxis_title="Modelo", yaxis_title="Cantidad")
    st.plotly_chart(fig1, use_container_width=True)

    mc_model = filtered.groupby(["instrument_type", "machine_config_status"], dropna=False).size().reset_index(name="Cantidad")
    fig2 = px.bar(mc_model, x="instrument_type", y="Cantidad", color="machine_config_status", barmode="group", text="Cantidad", title="Machine Configuration por modelo")
    fig2.update_layout(height=400, xaxis_title="Modelo", yaxis_title="Cantidad")
    st.plotly_chart(fig2, use_container_width=True)

    status_model = filtered.groupby(["instrument_type", "instrument_status_clean"], dropna=False).size().reset_index(name="Cantidad")
    fig3 = px.bar(status_model, x="instrument_type", y="Cantidad", color="instrument_status_clean", barmode="stack", text="Cantidad", title="Instrument Status por modelo")
    fig3.update_layout(height=440, xaxis_title="Modelo", yaxis_title="Cantidad", legend_title="Status")
    st.plotly_chart(fig3, use_container_width=True)

    # Details
    tabs = st.tabs(["Detalle general", "Machine Configuration incompleta", "Status", "Exportar ISR-Live filtrado"])
    detail_cols = ["distributor", "country", "instrument_type", "serial_number", "customer_name", "city", "instrument_status", "machine_config", "machine_config_status", "software_version", "os_version", "blood_bank"]
    with tabs[0]:
        st.dataframe(filtered[detail_cols], use_container_width=True, hide_index=True)
    with tabs[1]:
        bad = filtered[~filtered["machine_config_ok"]].copy()
        if bad.empty:
            st.success("Todos los instrumentos filtrados tienen Machine Configuration completa según las reglas actuales.")
        else:
            st.dataframe(bad[detail_cols], use_container_width=True, hide_index=True)
    with tabs[2]:
        status_tbl = filtered.groupby(["instrument_status_clean", "instrument_type"], dropna=False).size().reset_index(name="Cantidad")
        st.dataframe(status_tbl.sort_values(["instrument_status_clean", "instrument_type"]), use_container_width=True, hide_index=True)
    with tabs[3]:
        xlsx = to_excel({"ISR-Live Filtered": filtered[detail_cols], "Base by Model": base_model, "Machine Config": mc_model, "Status by Model": status_model})
        st.download_button(
            "Descargar análisis ISR-Live filtrado",
            data=xlsx,
            file_name=f"ISRLive_{safe_filename(meta['distributor'])}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

# ------------------------------------------------------------
# Exports
# ------------------------------------------------------------
def to_excel(sheets: Dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, df in sheets.items():
            sheet = re.sub(r"[\\/*?:\[\]]", "", name)[:31] or "Sheet"
            df.to_excel(writer, sheet_name=sheet, index=False)
    return output.getvalue()


def build_excel_report(snapshot: pd.DataFrame, summary: Dict, meta: Dict, reviewer: str, notes: str) -> bytes:
    executive = pd.DataFrame([
        {"Indicator": "Distributor", "Value": meta["distributor"]},
        {"Indicator": "Country", "Value": meta["country"]},
        {"Indicator": "Period", "Value": meta["period"]},
        {"Indicator": "Reviewer", "Value": reviewer},
        {"Indicator": "Overall Score", "Value": f"{summary['overall']}%"},
        {"Indicator": "Maturity", "Value": summary["maturity"]},
        {"Indicator": "Open/Partial Items", "Value": summary["open"]},
        {"Indicator": "Critical Items", "Value": summary["critical"]},
        {"Indicator": "Evidence Uploaded", "Value": f"{summary['evidence']}/{summary['total_questions']}"},
        {"Indicator": "General Notes", "Value": notes},
    ])
    return to_excel({
        "Executive Summary": executive,
        "Score by Category": summary["by_category"],
        "Assessment Items": snapshot,
        "Action Plan": snapshot[snapshot["Response"].isin(["P - Parcial", "N - No cumple"])],
    })


def build_pdf_report(snapshot: pd.DataFrame, summary: Dict, meta: Dict, reviewer: str, notes: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.1*cm, rightMargin=1.1*cm, topMargin=.9*cm, bottomMargin=.9*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("Title", parent=styles["Title"], alignment=TA_CENTER, fontSize=17, textColor=colors.HexColor("#0F172A"))
    h = ParagraphStyle("H", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0F172A"))
    normal = ParagraphStyle("N", parent=styles["Normal"], fontSize=7.5, leading=9, alignment=TA_LEFT)
    story = [Paragraph(APP_TITLE, title), Spacer(1, .25*cm)]
    story.append(Paragraph(f"<b>Distributor:</b> {meta['distributor']} &nbsp;&nbsp; <b>Country:</b> {meta['country']} &nbsp;&nbsp; <b>Period:</b> {meta['period']} &nbsp;&nbsp; <b>Reviewer:</b> {reviewer}", normal))
    story.append(Spacer(1, .25*cm))
    summary_data = [["Indicator", "Value"], ["Overall Score", f"{summary['overall']}%"], ["Maturity", summary["maturity"]], ["Open/Partial Items", str(summary["open"])], ["Critical Items", str(summary["critical"])], ["Evidence", f"{summary['evidence']}/{summary['total_questions']}"]]
    table = Table(summary_data, colWidths=[6*cm, 5*cm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#0F172A")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), .25, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0,0), (-1,-1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, .35*cm))
    story.append(Paragraph("Assessment Items", h))
    cols = ["Question ID", "Macro Category", "Item", "Response", "Risk", "Item Status", "Evidence Uploaded", "Action Plan"]
    data = [cols] + snapshot[cols].astype(str).values.tolist()
    data = [[Paragraph(str(c), normal) for c in row] for row in data]
    tbl = Table(data, colWidths=[1.7*cm, 4.2*cm, 4.1*cm, 2.6*cm, 2*cm, 2.4*cm, 2.4*cm, 8*cm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1E3A8A")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), .25, colors.HexColor("#E2E8F0")), ("FONTSIZE", (0,0), (-1,-1), 7),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
    ]))
    story.append(tbl)
    doc.build(story)
    return buffer.getvalue()

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="LATAM Service Assessment", page_icon="🧪", layout="wide")
    inject_css()
    render_header()
    meta = distributor_selector()

    if not meta["distributor"]:
        st.stop()

    tab1, tab2 = st.tabs(["Assessment corporativo", "Análisis ISR-Live"])
    with tab1:
        page_corporate(meta)
    with tab2:
        page_isrlive(meta)

if __name__ == "__main__":
    main()
