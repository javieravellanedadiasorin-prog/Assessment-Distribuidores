from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
    REPORTLAB_OK = True
except Exception:
    REPORTLAB_OK = False

APP_TITLE = "LATAM Distributor Service Excellence Assessment"
APP_SUBTITLE = "Futuristic Technical Health Check | ISR-Live + Evidence + Troubleshooting + Executive Report"
BASE_DIR = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
DATA_DIR = BASE_DIR / "data"
EVIDENCE_DIR = BASE_DIR / "evidence"
DB_PATH = DATA_DIR / "service_assessment.db"
DISTRIBUTOR_MASTER_PATH = DATA_DIR / "distributors_master.csv"
DISTRIBUTOR_MASTER_LATAM_PATH = DATA_DIR / "distributors_master_latam.csv"
DATA_DIR.mkdir(exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)

DEFAULT_TARGET_SW = {"LIAISON XL": "4.2.6.2", "LIAISON XL LAS": "4.2.6.2", "LIAISON XS": ""}
INVALID_CONFIG_VALUES = {
    "", "-", "--", "n/a", "na", "nan", "none", "null", "unknown",
    "dont know", "don't know", "do not know", "data not available",
    "data no available", "data no disponible", "no disponible", "sin informacion",
    "sin información", "not done", "no hecho", "pendiente", "tbc", "to be checked"
}
INACTIVE_STATUS_WORDS = ["scrap", "scrapped", "removed", "inactive", "decommissioned", "warehouse", "stock", "not installed", "retired"]
COLUMN_ALIASES = {
    "distributor": ["Distributor name", "Distributor", "Dealer", "Partner", "Distribuidor"],
    "instrument_type": ["Instrument type", "Instrument Type", "Model", "Instrument", "Tipo de instrumento", "Modelo", "Analyzer"],
    "customer_name": ["Customer name", "Customer", "Client", "Nombre cliente", "Cliente"],
    "country": ["Country", "Pais", "País"],
    "city": ["City", "Ciudad"],
    "address": ["Address", "Direccion", "Dirección"],
    "serial_number": ["Serial number", "Serial Number", "SN", "S/N", "Serial", "Numero de serie", "Número de serie", "N° Serie"],
    "installation_date": ["Installation date", "Installation Date", "Install date", "Fecha de instalación", "Fecha instalacion"],
    "machine_config": ["Machine Configurations", "Machine Configuration", "Machine config", "Configuration", "Configuración de máquina", "Configuracion de maquina", "Configuración", "Configuracion"],
    "instrument_status": ["Instrument Status", "Status", "Estado", "Operational Status", "Estado instrumento"],
    "software_version": ["Software version", "Software Version", "User SW", "User SW Version", "User Software", "SW Version", "SW", "Version", "Versión software", "Version software"],
    "os_version": ["Operating System", "OS", "OS Version", "Windows version", "Windows Version", "Sistema operativo"],
    "volume": ["Volume", "Volumen"],
    "contract_type": ["Type of contract", "Contract", "Contrato", "Tipo de contrato"],
}
TROUBLE_KEYWORDS = {
    "General error / failure": ["error", "err", "failed", "failure", "fault", "exception"],
    "Sample Integrity / SIE": ["sample integrity", "sie", "clot", "foam", "sample not detected"],
    "Reagent Integrity / RIE": ["reagent integrity", "rie", "integral", "expired", "invalid integral"],
    "Washer / WAF": ["washer", "waf", "wash", "dispense", "aspirate"],
    "Pipettor / Probe": ["pipettor", "probe", "sample arm", "reagent arm", "z axis", "x axis", "y axis"],
    "Incubator / Belt / Pulley": ["incubator", "belt", "pulley", "predicted value", "expected value"],
    "Barcode / Rack detection": ["barcode", "bcr", "rack detection", "scanner"],
    "Temperature": ["temperature", "temp", "thermal", "heater", "cooler"],
}

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def clean_text(value) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())

def norm(value) -> str:
    return clean_text(value).lower().replace("’", "'").replace("´", "'")

def norm_col(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())

def safe_filename(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return value[:150] or "file"

def clean_instrument_type(value: str) -> str:
    text = clean_text(value)
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    low = text.lower()
    if "xl las" in low:
        return "LIAISON XL LAS"
    if "liaison xl" in low or low == "xl" or "lxl" in low:
        return "LIAISON XL"
    if "liaison xs" in low or low == "xs" or "lxs" in low:
        return "LIAISON XS"
    return text or "Unknown"

def find_column(df: pd.DataFrame, logical_name: str) -> Optional[str]:
    normalized = {norm_col(c): c for c in df.columns}
    for alias in COLUMN_ALIASES.get(logical_name, []):
        key = norm_col(alias)
        if key in normalized:
            return normalized[key]
    flexible = {
        "serial_number": ["serial"], "instrument_type": ["instrument"],
        "machine_config": ["machine", "config"], "software_version": ["software"],
        "os_version": ["windows"], "instrument_status": ["status"]
    }
    tokens = flexible.get(logical_name)
    if tokens:
        for col in df.columns:
            c = str(col).lower()
            if all(t in c for t in tokens):
                return col
    return None

def read_table(uploaded_file) -> pd.DataFrame:
    """Lee CSV/XLSX exportado directamente desde ISR-Live.

    ISR-Live suele exportar CSV con separador punto y coma y valores tipo ="2210000000".
    Por eso se fuerza index_col=False y se hace fallback con QUOTE_NONE para evitar
    corrimientos de columnas cuando existen comillas no estándar.
    """
    suffix = Path(uploaded_file.name).suffix.lower()
    raw = bytes(uploaded_file.getbuffer())
    if suffix in [".xlsx", ".xlsm", ".xls"]:
        return pd.read_excel(io.BytesIO(raw), dtype=str)

    last_error = None
    for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
        try:
            text = raw.decode(enc)
            sample = text[:8000]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                sep = dialect.delimiter
            except Exception:
                sep = ";" if sample.count(";") > sample.count(",") else ","

            attempts = [
                {"quoting": csv.QUOTE_MINIMAL, "on_bad_lines": "skip"},
                {"quoting": csv.QUOTE_NONE, "on_bad_lines": "skip"},
            ]
            for opts in attempts:
                try:
                    df = pd.read_csv(
                        io.StringIO(text),
                        sep=sep,
                        dtype=str,
                        engine="python",
                        index_col=False,
                        **opts,
                    )
                    return cleanup_export_dataframe(df)
                except Exception as exc:
                    last_error = exc
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"No fue posible leer el archivo. Último error: {last_error}")


def cleanup_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Limpieza general para exportes CSV tipo ISR-Live."""
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    for col in out.columns:
        out[col] = out[col].apply(clean_excel_export_value)
    return out


def clean_excel_export_value(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    # Limpia patrones típicos de Excel/CSV: ="2210001948"
    match = re.fullmatch(r'=?"?([^"]*)"?', text)
    if match:
        text = match.group(1)
    return re.sub(r"\s+", " ", text).strip()

@st.cache_data(show_spinner=False)
def load_distributor_master(latam_only: bool = True) -> pd.DataFrame:
    """Carga el maestro de distribuidores generado desde Records_List_Report."""
    preferred = DISTRIBUTOR_MASTER_LATAM_PATH if latam_only and DISTRIBUTOR_MASTER_LATAM_PATH.exists() else DISTRIBUTOR_MASTER_PATH
    if not preferred.exists():
        return pd.DataFrame(columns=["Distributor", "Country", "World Region", "Commercial Region"])
    df = pd.read_csv(preferred, dtype=str, encoding="utf-8-sig").fillna("")
    for col in df.columns:
        df[col] = df[col].apply(clean_text)
    df = df[(df["Distributor"] != "") & (df["Country"] != "")]
    return df.drop_duplicates().sort_values(["Country", "Distributor"]).reset_index(drop=True)


def distributor_country_selector(prefix: str = "corporate") -> Tuple[str, str, str, str]:
    """Selector dependiente: distribuidor -> país, usando el maestro generado desde ISR-Live."""
    latam_only = st.toggle(
        "Mostrar únicamente distribuidores LATAM",
        value=True,
        key=f"{prefix}_latam_only",
        help="La lista viene del archivo Records_List_Report cargado. Puedes desactivar el filtro para ver todos los distribuidores globales del archivo.",
    )
    master = load_distributor_master(latam_only=latam_only)
    if master.empty:
        c1, c2 = st.columns(2)
        return c1.text_input("Distribuidor", key=f"{prefix}_distributor_free"), c2.text_input("País", key=f"{prefix}_country_free"), "", ""

    distributors = sorted(master["Distributor"].dropna().unique().tolist())
    current_distributor = st.session_state.get(f"{prefix}_selected_distributor", distributors[0] if distributors else "")
    if current_distributor not in distributors:
        current_distributor = distributors[0] if distributors else ""

    c1, c2, c3, c4 = st.columns([2.0, 1.4, 1.2, 1.2])
    distributor = c1.selectbox(
        "Distribuidor",
        options=distributors,
        index=distributors.index(current_distributor) if current_distributor in distributors else 0,
        key=f"{prefix}_selected_distributor",
    )

    filtered = master[master["Distributor"] == distributor].copy()
    countries = sorted(filtered["Country"].dropna().unique().tolist())
    current_country = st.session_state.get(f"{prefix}_selected_country", countries[0] if countries else "")
    if current_country not in countries:
        current_country = countries[0] if countries else ""

    country = c2.selectbox(
        "País",
        options=countries,
        index=countries.index(current_country) if current_country in countries else 0,
        key=f"{prefix}_selected_country",
    )

    row = filtered[filtered["Country"] == country].head(1)
    world_region = clean_text(row["World Region"].iloc[0]) if not row.empty and "World Region" in row.columns else ""
    commercial_region = clean_text(row["Commercial Region"].iloc[0]) if not row.empty and "Commercial Region" in row.columns else ""
    c3.text_input("World Region", value=world_region, disabled=True, key=f"{prefix}_world_region")
    c4.text_input("Commercial Region", value=commercial_region, disabled=True, key=f"{prefix}_commercial_region")

    return distributor, country, world_region, commercial_region


def period_selector(prefix: str = "corporate") -> Tuple[date, date, str]:
    today = date.today()
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    default_start = date(today.year, quarter_start_month, 1)
    default_end = today
    c1, c2 = st.columns(2)
    start = c1.date_input("Fecha de inicio", value=st.session_state.get(f"{prefix}_period_start", default_start), key=f"{prefix}_period_start")
    end = c2.date_input("Fecha de finalización", value=st.session_state.get(f"{prefix}_period_end", default_end), key=f"{prefix}_period_end")
    if start > end:
        st.warning("La fecha de inicio no puede ser posterior a la fecha de finalización. Ajusté el periodo visualmente para el reporte.")
        start, end = end, start
    label = f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"
    return start, end, label


def is_active(status: str) -> bool:
    low = norm(status)
    return not low or not any(word in low for word in INACTIVE_STATUS_WORDS)

def is_bad_machine_config(value: str) -> bool:
    low = norm(value)
    return low in INVALID_CONFIG_VALUES or len(low) < 3

def parse_version(value: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", clean_text(value))
    return tuple(int(x) for x in nums[:6]) if nums else tuple()

def version_ok(current: str, target: str) -> Optional[bool]:
    if not clean_text(target):
        return None
    c, t = parse_version(current), parse_version(target)
    if not c or not t:
        return None
    max_len = max(len(c), len(t))
    c += (0,) * (max_len - len(c))
    t += (0,) * (max_len - len(t))
    return c >= t

def bool_icon(value) -> str:
    if value is True or value == 1:
        return "✅"
    if value is False or value == 0:
        return "❌"
    return "⚪"

def weighted_score(checks: List[Tuple[str, Optional[bool], int]]) -> float:
    possible = sum(w for _, ok, w in checks if ok is not None)
    earned = sum(w for _, ok, w in checks if ok is True)
    return round(earned / possible * 100, 1) if possible else 0.0

def risk_from_findings(score: float, machine_config_ok: bool, software_ok_value: Optional[bool], missing_data: bool) -> str:
    if machine_config_ok is False and software_ok_value is False:
        return "Critical"
    if score < 60:
        return "Critical"
    if score < 75:
        return "High"
    if score < 90 or missing_data:
        return "Medium"
    return "Low"

def status_from_score(score: float, risk: str) -> str:
    if risk in ["Critical", "High"] or score < 75:
        return "Non-compliant"
    if risk == "Medium" or score < 90:
        return "Partial"
    return "Compliant"

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, source_file TEXT,
        distributor TEXT, country TEXT, total_instruments INTEGER, active_instruments INTEGER,
        global_score REAL, summary_json TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS instrument_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT, assessment_id INTEGER, serial_number TEXT,
        instrument_type TEXT, customer_name TEXT, country TEXT, city TEXT, instrument_status TEXT,
        machine_config TEXT, software_version TEXT, os_version TEXT, active INTEGER,
        machine_config_ok INTEGER, software_ok INTEGER, os_ok INTEGER, data_quality_ok INTEGER,
        score REAL, risk TEXT, status TEXT, findings_json TEXT, raw_json TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, serial_number TEXT NOT NULL,
        visit_date TEXT, visit_type TEXT, engineer TEXT, customer_contact TEXT, risk TEXT,
        summary TEXT, conclusion TEXT, next_action TEXT, filename TEXT, stored_path TEXT,
        file_type TEXT, file_size INTEGER)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS troubleshooting (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, serial_number TEXT NOT NULL,
        source_file TEXT, total_files INTEGER, total_lines INTEGER, total_hits INTEGER,
        category_json TEXT, highlights_json TEXT, recommendation TEXT)""")
    conn.commit(); conn.close()

def nullable_bool_to_int(value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return int(bool(value))

def save_assessment(df_result: pd.DataFrame, summary: Dict, source_file: str) -> int:
    distributor = next((clean_text(x) for x in df_result.get("distributor", pd.Series(dtype=str)).tolist() if clean_text(x)), "")
    country = next((clean_text(x) for x in df_result.get("country", pd.Series(dtype=str)).tolist() if clean_text(x)), "")
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO assessments (created_at, source_file, distributor, country,
        total_instruments, active_instruments, global_score, summary_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", (now_str(), source_file, distributor, country,
        int(summary.get("total", 0)), int(summary.get("active", 0)), float(summary.get("global_score", 0)),
        json.dumps(summary, ensure_ascii=False)))
    aid = cur.lastrowid
    for _, r in df_result.iterrows():
        cur.execute("""INSERT INTO instrument_results (assessment_id, serial_number, instrument_type,
            customer_name, country, city, instrument_status, machine_config, software_version,
            os_version, active, machine_config_ok, software_ok, os_ok, data_quality_ok, score,
            risk, status, findings_json, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, clean_text(r.get("serial_number", "")), clean_text(r.get("instrument_type", "")),
            clean_text(r.get("customer_name", "")), clean_text(r.get("country", "")), clean_text(r.get("city", "")),
            clean_text(r.get("instrument_status", "")), clean_text(r.get("machine_config", "")),
            clean_text(r.get("software_version", "")), clean_text(r.get("os_version", "")), int(bool(r.get("active", False))),
            nullable_bool_to_int(r.get("machine_config_ok")), nullable_bool_to_int(r.get("software_ok")),
            nullable_bool_to_int(r.get("os_ok")), nullable_bool_to_int(r.get("data_quality_ok")), float(r.get("score", 0)),
            clean_text(r.get("risk", "")), clean_text(r.get("status", "")), json.dumps(r.get("findings", []), ensure_ascii=False),
            json.dumps(r.get("raw", {}), ensure_ascii=False, default=str)))
    conn.commit(); conn.close(); return int(aid)

def load_history(limit: int = 50) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("""SELECT id, created_at, source_file, distributor, country,
        total_instruments, active_instruments, global_score FROM assessments ORDER BY id DESC LIMIT ?""", conn, params=(limit,))
    conn.close(); return df

def save_evidence(sn: str, fields: Dict, uploaded_file) -> None:
    serial_dir = EVIDENCE_DIR / safe_filename(sn); serial_dir.mkdir(parents=True, exist_ok=True)
    content = bytes(uploaded_file.getbuffer())
    stored_path = serial_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_filename(uploaded_file.name)}"
    stored_path.write_bytes(content)
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO evidence (created_at, serial_number, visit_date, visit_type, engineer,
        customer_contact, risk, summary, conclusion, next_action, filename, stored_path, file_type, file_size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (now_str(), sn, fields.get("visit_date", ""),
        fields.get("visit_type", ""), fields.get("engineer", ""), fields.get("customer_contact", ""), fields.get("risk", ""),
        fields.get("summary", ""), fields.get("conclusion", ""), fields.get("next_action", ""), uploaded_file.name,
        str(stored_path), uploaded_file.type, len(content)))
    conn.commit(); conn.close()

def load_evidence(sn: Optional[str] = None) -> pd.DataFrame:
    conn = get_conn()
    if sn:
        df = pd.read_sql_query("SELECT * FROM evidence WHERE serial_number = ? ORDER BY id DESC", conn, params=(sn,))
    else:
        df = pd.read_sql_query("SELECT * FROM evidence ORDER BY id DESC", conn)
    conn.close(); return df

def save_troubleshooting(sn: str, filename: str, analysis: Dict) -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO troubleshooting (created_at, serial_number, source_file, total_files,
        total_lines, total_hits, category_json, highlights_json, recommendation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now_str(), sn, filename, int(analysis.get("total_files", 0)), int(analysis.get("total_lines", 0)),
        int(analysis.get("total_hits", 0)), json.dumps(analysis.get("categories", {}), ensure_ascii=False),
        json.dumps(analysis.get("highlights", []), ensure_ascii=False), analysis.get("recommendation", "")))
    conn.commit(); conn.close()

def load_troubleshooting(sn: Optional[str] = None) -> pd.DataFrame:
    conn = get_conn()
    if sn:
        df = pd.read_sql_query("SELECT * FROM troubleshooting WHERE serial_number = ? ORDER BY id DESC", conn, params=(sn,))
    else:
        df = pd.read_sql_query("SELECT * FROM troubleshooting ORDER BY id DESC", conn)
    conn.close(); return df

def standardize(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    out = df.copy(); mapping = {}
    for logical in COLUMN_ALIASES:
        col = find_column(out, logical); mapping[logical] = col
        out[f"__{logical}"] = out[col].apply(clean_text) if col else ""
    out["__serial_number"] = out["__serial_number"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    out["__instrument_type"] = out["__instrument_type"].apply(clean_instrument_type)
    return out, mapping

def evaluate(df: pd.DataFrame, target_sw: Dict[str, str], only_active: bool = True) -> Tuple[pd.DataFrame, Dict, Dict]:
    std, mapping = standardize(df); rows = []
    for idx, r in std.iterrows():
        serial = clean_text(r.get("__serial_number", "")); instrument = clean_instrument_type(r.get("__instrument_type", ""))
        customer = clean_text(r.get("__customer_name", "")); country = clean_text(r.get("__country", "")); city = clean_text(r.get("__city", ""))
        distributor = clean_text(r.get("__distributor", "")); status = clean_text(r.get("__instrument_status", ""))
        machine_config = clean_text(r.get("__machine_config", "")); software = clean_text(r.get("__software_version", "")); os_version = clean_text(r.get("__os_version", ""))
        active = is_active(status); findings = []
        raw = r.drop(labels=[x for x in r.index if str(x).startswith("__")], errors="ignore").to_dict()
        if only_active and not active:
            rows.append({"row": idx + 1, "serial_number": serial, "instrument_type": instrument, "customer_name": customer, "country": country, "city": city, "distributor": distributor, "instrument_status": status, "machine_config": machine_config, "software_version": software, "os_version": os_version, "active": False, "machine_config_ok": None, "software_ok": None, "os_ok": None, "data_quality_ok": None, "score": np.nan, "risk": "Not evaluable", "status": "Not evaluable", "findings": ["Instrumento no activo o fuera de rutina. No incluido en el score operativo."], "raw": raw})
            continue
        checks = []
        serial_ok = bool(serial); checks.append(("Serial number", serial_ok, 10))
        if not serial_ok: findings.append("Serial number vacío o no identificado.")
        instrument_ok = bool(instrument and instrument != "Unknown"); checks.append(("Instrument type", instrument_ok, 10))
        if not instrument_ok: findings.append("Tipo de instrumento vacío o no identificable.")
        missing = []
        for field, label in [("__customer_name", "Customer name"), ("__country", "Country"), ("__city", "City"), ("__instrument_status", "Instrument Status")]:
            if not clean_text(r.get(field, "")): missing.append(label)
        data_quality_ok = len(missing) == 0; checks.append(("Data quality", data_quality_ok, 15))
        if not data_quality_ok: findings.append("Faltan campos básicos en ISR-Live: " + ", ".join(missing))
        machine_config_ok = not is_bad_machine_config(machine_config); checks.append(("Machine Configuration", machine_config_ok, 30))
        if not machine_config_ok: findings.append("Machine Configuration incompleta, vacía o con valor inválido. No se aceptan Don't know, Data not available, Data no disponible, Not done ni equivalentes.")
        target = clean_text(target_sw.get(instrument, "")); software_ok_value = version_ok(software, target)
        if not target:
            checks.append(("Software", None, 20)); findings.append(f"No hay versión objetivo configurada para {instrument}.")
        elif not software:
            checks.append(("Software", False, 20)); findings.append(f"Software version vacío. Versión objetivo configurada: {target}."); software_ok_value = False
        elif software_ok_value is None:
            checks.append(("Software", None, 20)); findings.append(f"No fue posible comparar software actual '{software}' contra objetivo '{target}'.")
        else:
            checks.append(("Software", software_ok_value, 20))
            if not software_ok_value: findings.append(f"Software no actualizado. Actual: {software}. Objetivo: {target}.")
        os_ok = None
        if not os_version:
            findings.append("Sistema operativo no disponible en el archivo.")
        else:
            low_os = os_version.lower()
            if "vista" in low_os or "windows 7" in low_os or "win7" in low_os:
                os_ok = False; findings.append(f"Sistema operativo no cumple mínimo esperado: {os_version}.")
            elif "windows 10" in low_os or "win10" in low_os or "windows 11" in low_os:
                os_ok = True
        checks.append(("Operating System", os_ok, 15))
        score = weighted_score(checks); risk = risk_from_findings(score, machine_config_ok, software_ok_value, not data_quality_ok); eval_status = status_from_score(score, risk)
        if not findings: findings.append("Sin hallazgos críticos según las reglas configuradas.")
        rows.append({"row": idx + 1, "serial_number": serial, "instrument_type": instrument, "customer_name": customer, "country": country, "city": city, "distributor": distributor, "instrument_status": status, "machine_config": machine_config, "software_version": software, "os_version": os_version, "active": active, "machine_config_ok": machine_config_ok, "software_ok": software_ok_value, "os_ok": os_ok, "data_quality_ok": data_quality_ok, "score": score, "risk": risk, "status": eval_status, "findings": findings, "raw": raw})
    result = pd.DataFrame(rows); return result, summarize(result), mapping

def summarize(result: pd.DataFrame) -> Dict:
    if result.empty: return {"global_score": 0, "total": 0, "active": 0}
    active = result[result["active"] == True].copy(); evaluable = active[active["score"].notna()].copy()
    return {"global_score": round(float(evaluable["score"].mean()), 1) if not evaluable.empty else 0,
        "total": int(len(result)), "active": int(len(active)), "compliant": int((active["status"] == "Compliant").sum()),
        "partial": int((active["status"] == "Partial").sum()), "non_compliant": int((active["status"] == "Non-compliant").sum()),
        "critical": int((active["risk"] == "Critical").sum()), "high": int((active["risk"] == "High").sum()),
        "machine_config_missing": int((active["machine_config_ok"] == False).sum()), "software_not_ok": int((active["software_ok"] == False).sum()),
        "data_quality_not_ok": int((active["data_quality_ok"] == False).sum())}

def action_plan(result: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in result.iterrows():
        if not bool(r.get("active", False)): continue
        base = {"Serial number": r.get("serial_number", ""), "Instrument": r.get("instrument_type", ""), "Customer": r.get("customer_name", ""), "Risk": r.get("risk", "")}
        if r.get("machine_config_ok") is False:
            rows.append({**base, "Priority": "High", "Finding": "Machine Configuration incompleta o inválida", "Required action": "Actualizar Machine Configuration en ISR-Live con información real del equipo.", "Expected evidence": "CSV/Screenshot ISR-Live actualizado", "Owner": "Distributor FSE / Service Leader", "Status": "Open"})
        if r.get("software_ok") is False:
            rows.append({**base, "Priority": "High", "Finding": "Software no actualizado", "Required action": "Planificar actualización de software y documentar ejecución.", "Expected evidence": "Screenshot versión SW / service report", "Owner": "Distributor FSE / DiaSorin", "Status": "Open"})
        if r.get("data_quality_ok") is False:
            rows.append({**base, "Priority": "Medium", "Finding": "Datos básicos incompletos en ISR-Live", "Required action": "Completar cliente, país, ciudad y estado operativo.", "Expected evidence": "CSV ISR-Live actualizado", "Owner": "Distributor Admin / Service Leader", "Status": "Open"})
        if r.get("os_ok") is False:
            rows.append({**base, "Priority": "High", "Finding": "Sistema operativo no cumple", "Required action": "Revisar compatibilidad y planificar actualización/migración.", "Expected evidence": "Screenshot OS / service report", "Owner": "Distributor FSE / DiaSorin", "Status": "Open"})
    return pd.DataFrame(rows)

def display_result_df(result: pd.DataFrame) -> pd.DataFrame:
    if result.empty: return result
    df = result.copy(); df["Machine Config OK"] = df["machine_config_ok"].apply(bool_icon); df["Software OK"] = df["software_ok"].apply(bool_icon); df["OS OK"] = df["os_ok"].apply(bool_icon); df["Data OK"] = df["data_quality_ok"].apply(bool_icon); df["Findings"] = df["findings"].apply(lambda x: " | ".join(x) if isinstance(x, list) else str(x))
    return df[["serial_number", "instrument_type", "customer_name", "country", "city", "instrument_status", "machine_config", "software_version", "os_version", "Machine Config OK", "Software OK", "OS OK", "Data OK", "score", "risk", "status", "Findings"]].rename(columns={"serial_number": "Serial Number", "instrument_type": "Instrument", "customer_name": "Customer", "instrument_status": "Instrument Status", "machine_config": "Machine Configuration", "software_version": "Software Version", "os_version": "OS Version", "score": "Score", "risk": "Risk", "status": "Status"})

def read_text_safely(data: bytes) -> str:
    for enc in ["utf-8", "utf-8-sig", "latin1", "cp1252", "utf-16"]:
        try: return data.decode(enc, errors="ignore")
        except Exception: pass
    return data.decode("latin1", errors="ignore")

def analyze_troubleshooting_file(uploaded_file) -> Dict:
    raw = bytes(uploaded_file.getbuffer()); files = []
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
            for info in z.infolist():
                if info.is_dir() or info.file_size > 20_000_000: continue
                name = info.filename
                if not name.lower().endswith((".txt", ".log", ".csv", ".xml", ".ini")): continue
                try: files.append((name, read_text_safely(z.read(info))))
                except Exception: continue
    else:
        files.append((uploaded_file.name, read_text_safely(raw)))
    return analyze_texts(files)

def analyze_texts(files: List[Tuple[str, str]]) -> Dict:
    categories = Counter(); highlights = []; total_lines = 0; total_hits = 0
    for filename, text in files:
        lines = text.splitlines(); total_lines += len(lines)
        for n, line in enumerate(lines, start=1):
            low = line.lower(); matched = []
            for cat, keywords in TROUBLE_KEYWORDS.items():
                if any(k in low for k in keywords): matched.append(cat); categories[cat] += 1
            if matched:
                total_hits += 1
                if len(highlights) < 150: highlights.append({"file": filename, "line": n, "category": ", ".join(sorted(set(matched))), "text": line[:600]})
    return {"total_files": len(files), "total_lines": total_lines, "total_hits": total_hits, "categories": dict(categories), "highlights": highlights, "recommendation": make_trouble_recommendation(categories, total_hits)}

def make_trouble_recommendation(categories: Counter, total_hits: int) -> str:
    if total_hits == 0: return "No se identificaron patrones evidentes con las reglas base. Revisar manualmente si el caso persiste."
    top = [x[0] for x in categories.most_common(3)]; recs = []
    if "Sample Integrity / SIE" in top: recs.append("Validar trazabilidad por Sample ID, presencia de clot/foam y eventos antes/después del SIE.")
    if "Reagent Integrity / RIE" in top: recs.append("Revisar integral/reactivo, estabilidad, vencimiento, carga y eventos RIE.")
    if "Washer / WAF" in top: recs.append("Analizar tendencias WAF/washer, aspiración, dispensación y posibles obstrucciones.")
    if "Incubator / Belt / Pulley" in top: recs.append("Revisar incubator belt, pulleys, tensión, alineación y errores de predicted/expected value.")
    if "Barcode / Rack detection" in top: recs.append("Validar scanner, barcode, rack detection y configuración de sample racks.")
    if "Pipettor / Probe" in top: recs.append("Verificar probe/pipettor, teach, ejes, obstrucciones y movimientos mecánicos.")
    return " ".join(recs) if recs else "Priorizar revisión de líneas con error/failure/exception y correlacionar con la hora del evento reportado."

def to_excel_bytes(sheets: Dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for sheet, df in sheets.items(): df.to_excel(writer, sheet_name=sheet[:31], index=False)
    return out.getvalue()

def make_pdf_report(result: pd.DataFrame, summary: Dict, plan: pd.DataFrame) -> bytes:
    if not REPORTLAB_OK: raise RuntimeError("ReportLab no está instalado.")
    buffer = io.BytesIO(); doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.2*cm, rightMargin=1.2*cm, topMargin=1.0*cm, bottomMargin=1.0*cm)
    styles = getSampleStyleSheet(); title = ParagraphStyle("CustomTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=18); normal = ParagraphStyle("CustomNormal", parent=styles["Normal"], fontSize=8, leading=10); h2 = ParagraphStyle("CustomH2", parent=styles["Heading2"], fontSize=12, leading=14)
    story = [Paragraph(APP_TITLE, title), Paragraph(APP_SUBTITLE, normal), Spacer(1, .4*cm)]
    summary_rows = [["Indicador", "Resultado"], ["Score global", f"{summary.get('global_score',0)}%"], ["Instrumentos totales", str(summary.get("total",0))], ["Instrumentos activos evaluados", str(summary.get("active",0))], ["Cumplen", str(summary.get("compliant",0))], ["Parciales", str(summary.get("partial",0))], ["No cumplen", str(summary.get("non_compliant",0))], ["Riesgos críticos", str(summary.get("critical",0))], ["Machine Configuration pendiente", str(summary.get("machine_config_missing",0))], ["Software no actualizado", str(summary.get("software_not_ok",0))]]
    table = Table(summary_rows, colWidths=[8*cm, 5*cm]); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E79")), ("TEXTCOLOR",(0,0),(-1,0),colors.white), ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("GRID",(0,0),(-1,-1),.25,colors.HexColor("#CCCCCC")), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F4F6F8")]), ("FONTSIZE",(0,0),(-1,-1),8)])); story.append(table)
    story += [Spacer(1, .5*cm), Paragraph("Resultados por instrumento", h2)]
    cols = ["serial_number","instrument_type","customer_name","machine_config_ok","software_ok","score","risk","status"]; df = result[cols].head(45).copy() if not result.empty else pd.DataFrame(columns=cols); df.columns = ["SN","Instrumento","Cliente","Machine Config","Software","Score","Riesgo","Estado"]
    rows = [[Paragraph(str(c), normal) for c in row] for row in ([list(df.columns)] + df.astype(str).values.tolist())]
    table2 = Table(rows, colWidths=[3*cm,3.2*cm,6*cm,3*cm,2.5*cm,2*cm,2.5*cm,3*cm]); table2.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E79")), ("TEXTCOLOR",(0,0),(-1,0),colors.white), ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("GRID",(0,0),(-1,-1),.25,colors.HexColor("#DDDDDD")), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F7F7F7")]), ("FONTSIZE",(0,0),(-1,-1),7), ("VALIGN",(0,0),(-1,-1),"TOP") ])); story.append(table2)
    story += [PageBreak(), Paragraph("Plan de acción", h2)]
    if plan.empty: story.append(Paragraph("No se generaron acciones abiertas con las reglas actuales.", normal))
    else:
        cols = ["Serial number","Customer","Priority","Finding","Required action","Expected evidence","Owner","Status"]; dfp = plan[cols].head(50).copy(); rows = [[Paragraph(str(c), normal) for c in row] for row in ([list(dfp.columns)] + dfp.astype(str).values.tolist())]
        table3 = Table(rows, colWidths=[2.6*cm,4*cm,2*cm,5*cm,8*cm,5*cm,4*cm,2*cm]); table3.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#7A1F1F")), ("TEXTCOLOR",(0,0),(-1,0),colors.white), ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("GRID",(0,0),(-1,-1),.25,colors.HexColor("#DDDDDD")), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white, colors.HexColor("#F7F7F7")]), ("FONTSIZE",(0,0),(-1,-1),7), ("VALIGN",(0,0),(-1,-1),"TOP") ])); story.append(table3)
    doc.build(story); return buffer.getvalue()

def css():
    st.markdown("""
    <style>
    :root {
        --bg: #07111f;
        --panel: rgba(15, 23, 42, 0.72);
        --cyan: #22d3ee;
        --blue: #2563eb;
        --teal: #14b8a6;
        --line: rgba(34, 211, 238, .35);
        --soft: rgba(148, 163, 184, .16);
    }
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(34,211,238,.14), transparent 30%),
            radial-gradient(circle at top right, rgba(37,99,235,.16), transparent 28%),
            linear-gradient(180deg, #07111f 0%, #0b1220 48%, #0f172a 100%);
    }
    .main .block-container {padding-top:1.2rem;max-width:1560px;}
    .header {
        position: relative;
        overflow: hidden;
        padding: 1.35rem 1.55rem;
        border-radius: 24px;
        background:
            linear-gradient(135deg, rgba(15,23,42,.96) 0%, rgba(30,58,138,.92) 48%, rgba(13,148,136,.90) 100%);
        color:white;
        margin-bottom:1rem;
        border: 1px solid rgba(125, 211, 252, .36);
        box-shadow: 0 22px 60px rgba(0,0,0,.35), inset 0 0 40px rgba(34,211,238,.08);
    }
    .header:after {
        content: "";
        position:absolute;
        inset:-60px -120px auto auto;
        width:360px;height:220px;
        background: radial-gradient(circle, rgba(34,211,238,.32), transparent 65%);
        transform: rotate(12deg);
    }
    .header h1 {margin:0;font-size:1.95rem;letter-spacing:.02em;font-weight:800;}
    .header p {margin:.35rem 0 0 0;color:#dbeafe;font-size:.98rem;}
    div[data-testid='stMetric'] {
        background: linear-gradient(180deg, rgba(15,23,42,.78), rgba(15,23,42,.46));
        border: 1px solid rgba(34,211,238,.22);
        border-radius: 18px;
        padding: .85rem 1rem;
        box-shadow: 0 10px 30px rgba(2,8,23,.20);
    }
    div[data-testid='stMetricValue'] {font-size:1.72rem;color:#e0f2fe;font-weight:800;}
    div[data-testid='stMetricLabel'] {color:#bae6fd;}
    section[data-testid='stSidebar'] {
        background: linear-gradient(180deg, #020617 0%, #0f172a 100%);
        border-right: 1px solid rgba(34,211,238,.20);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: .35rem;
        background: rgba(15,23,42,.35);
        padding:.35rem;
        border-radius: 16px;
        border: 1px solid rgba(34,211,238,.16);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        color: #bfdbfe;
        padding: .55rem .8rem;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(34,211,238,.22), rgba(37,99,235,.25));
        color: white;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 18px;
        border: 1px solid rgba(34,211,238,.16);
        overflow: hidden;
    }
    .tech-card {
        padding: 1rem 1.15rem;
        border-radius: 20px;
        border: 1px solid rgba(34,211,238,.24);
        background: linear-gradient(180deg, rgba(15,23,42,.62), rgba(15,23,42,.32));
        box-shadow: 0 12px 35px rgba(2,8,23,.24);
    }
    </style>
    """, unsafe_allow_html=True)

def header():
    st.markdown(f"<div class='header'><h1>{APP_TITLE}</h1><p>{APP_SUBTITLE}</p></div>", unsafe_allow_html=True)

def sidebar_config() -> Dict[str, str]:
    st.sidebar.header("Reglas de cumplimiento"); st.sidebar.caption("Configura la versión objetivo de software por plataforma.")
    if "target_sw" not in st.session_state: st.session_state["target_sw"] = DEFAULT_TARGET_SW.copy()
    target_sw = st.session_state["target_sw"]
    for model in list(DEFAULT_TARGET_SW.keys()): target_sw[model] = st.sidebar.text_input(f"Software objetivo - {model}", value=target_sw.get(model, ""))
    st.session_state["target_sw"] = target_sw; return target_sw

def render_metrics(summary: Dict):
    c1,c2,c3,c4,c5 = st.columns(5); c1.metric("Score global", f"{summary.get('global_score',0)}%"); c2.metric("Activos evaluados", summary.get("active",0)); c3.metric("Cumplen", summary.get("compliant",0)); c4.metric("No cumplen", summary.get("non_compliant",0)); c5.metric("Riesgos críticos", summary.get("critical",0))
    c6,c7,c8 = st.columns(3); c6.metric("Machine Config pendiente", summary.get("machine_config_missing",0)); c7.metric("Software no actualizado", summary.get("software_not_ok",0)); c8.metric("Datos incompletos", summary.get("data_quality_not_ok",0))

def render_charts(result: pd.DataFrame):
    if result.empty: return
    active = result[result["active"] == True].copy()
    if active.empty: st.warning("No hay instrumentos activos evaluables con el filtro actual."); return
    c1,c2 = st.columns(2)
    with c1:
        df = active["status"].value_counts().reset_index(); df.columns = ["Status","Count"]; st.plotly_chart(px.pie(df, names="Status", values="Count", hole=.55, title="Cumplimiento operativo"), use_container_width=True)
    with c2:
        df = active["risk"].value_counts().reset_index(); df.columns = ["Risk","Count"]; st.plotly_chart(px.bar(df, x="Risk", y="Count", text="Count", title="Riesgo por instrumento"), use_container_width=True)
    by_model = active.groupby("instrument_type", dropna=False).agg(Instruments=("serial_number","count"), AvgScore=("score","mean"), MissingMachineConfig=("machine_config_ok", lambda s:int((s==False).sum())), SoftwareNotOK=("software_ok", lambda s:int((s==False).sum()))).reset_index(); by_model["AvgScore"] = by_model["AvgScore"].round(1)
    st.plotly_chart(px.bar(by_model, x="instrument_type", y="AvgScore", text="AvgScore", hover_data=["Instruments","MissingMachineConfig","SoftwareNotOK"], title="Score promedio por modelo"), use_container_width=True)


# ============================================================
# Corporate assessment checklist loaded from original Excel format
# ============================================================

CORPORATE_CATEGORY_WEIGHTS = {
    "Installed Base Certification": 20,
    "Contact List": 10,
    "DiaSorin Accounts Optimization": 10,
    "Technical Evaluation": 15,
    "Service Tools": 15,
    "Stock Level": 10,
    "Service Traceability System": 15,
    "Customer Visit": 5,
}

DEFAULT_CORPORATE_ITEMS = [
    {
        "Macro Category": "Installed Base Certification",
        "Item": "Installed Base Update",
        "Definition": "Performed the installed base certification. Get the installed base certification format signed.",
        "Needed In Advance": "",
        "Evidence Required": "Signed installed base certification letter; ISR-Live export; supporting evidence uploaded by distributor.",
    },
    {
        "Macro Category": "Installed Base Certification",
        "Item": "System Configuration",
        "Definition": "Update all systems: no 'data not available' nor 'don't know' allowed to be left in the fields.",
        "Needed In Advance": "LIAISON XL: PC Model, OS and User SW Version. LIAISON XS: User SW Version. LQS: OS and PC Model.",
        "Evidence Required": "ISR-Live CSV showing Machine Configuration complete for every active SN; no Don't know, Data not available, Not done or blank values.",
    },
    {
        "Macro Category": "Installed Base Certification",
        "Item": "Customer Data",
        "Definition": "All customer data shall be reported into ISR-Live.",
        "Needed In Advance": "",
        "Evidence Required": "ISR-Live export with customer name, country, city, address and key customer fields completed.",
    },
    {
        "Macro Category": "Installed Base Certification",
        "Item": "System Status",
        "Definition": "Update the system status of all systems.",
        "Needed In Advance": "",
        "Evidence Required": "ISR-Live export showing correct operational status for each system: in routine, scrapped, stock, removed, demo, etc.",
    },
    {
        "Macro Category": "Installed Base Certification",
        "Item": "PM Planner",
        "Definition": "ISR-Live PM Planner shall contain the information of at least the last 3 PMs performed on each system. Not required for new systems that have never been installed.",
        "Needed In Advance": "Work orders of all PMs performed within the last 12 months up until the assessment is done.",
        "Evidence Required": "PM Planner export or screenshots; work orders for the last 12 months; evidence of last 3 PMs per applicable system.",
    },
    {
        "Macro Category": "Installed Base Certification",
        "Item": "PM Completion Evaluation (%)",
        "Definition": "Evaluate the percentage of completion of every quarter until this assessment is performed. Define an action plan for overdue PMs.",
        "Needed In Advance": "",
        "Evidence Required": "PM completion table by quarter; overdue PM list; corrective action plan.",
    },
    {
        "Macro Category": "Installed Base Certification",
        "Item": "PM Plan",
        "Definition": "Define a calendar with the dates when all future PMs will be performed during the rest of the year.",
        "Needed In Advance": "",
        "Evidence Required": "PM calendar for remaining year by customer, SN, quarter and responsible FSE.",
    },
    {
        "Macro Category": "Installed Base Certification",
        "Item": "PM Kit Stock",
        "Definition": "Evaluate the amount of PM kits available in the country versus the PMs to be performed during the rest of the year.",
        "Needed In Advance": "",
        "Evidence Required": "PM kit stock file; remaining PM demand; gap analysis.",
    },
    {
        "Macro Category": "Contact List",
        "Item": "Contacts",
        "Definition": "Get the full contact list of all relevant people working with DiaSorin: email, phone number, position and responsibilities.",
        "Needed In Advance": "",
        "Evidence Required": "Updated contact list with service, applications, logistics, management and escalation contacts.",
    },
    {
        "Macro Category": "Contact List",
        "Item": "FSE and AS Training Status",
        "Definition": "Evaluate the training status of all FSEs and ASs currently servicing DiaSorin instruments.",
        "Needed In Advance": "",
        "Evidence Required": "Training matrix by engineer, platform, level, certification status and expiration/retraining needs.",
    },
    {
        "Macro Category": "Contact List",
        "Item": "ISR - Live",
        "Definition": "Update ISR-Live contact list.",
        "Needed In Advance": "",
        "Evidence Required": "Screenshot or export showing updated contacts in ISR-Live.",
    },
    {
        "Macro Category": "DiaSorin Accounts Optimization",
        "Item": "Bomgar",
        "Definition": "Open accounts as needed. Close accounts as needed.",
        "Needed In Advance": "",
        "Evidence Required": "List of active BeyondTrust/Bomgar accounts; users to create; users to remove; justification.",
    },
    {
        "Macro Category": "DiaSorin Accounts Optimization",
        "Item": "TCM",
        "Definition": "Review TCM account access. Open accounts as needed and close accounts as needed.",
        "Needed In Advance": "",
        "Evidence Required": "List of active TCM accounts; users to create/remove.",
    },
    {
        "Macro Category": "DiaSorin Accounts Optimization",
        "Item": "Apparound",
        "Definition": "Review Apparound account access. Open accounts as needed and close accounts as needed.",
        "Needed In Advance": "",
        "Evidence Required": "List of active Apparound accounts; users to create/remove.",
    },
    {
        "Macro Category": "DiaSorin Accounts Optimization",
        "Item": "Filezilla",
        "Definition": "Review FileZilla/FTPS account access. Open accounts as needed and close accounts as needed.",
        "Needed In Advance": "",
        "Evidence Required": "List of active FTPS/FileZilla accounts; users to create/remove.",
    },
    {
        "Macro Category": "DiaSorin Accounts Optimization",
        "Item": "ISR - Live",
        "Definition": "Review ISR-Live account access. Open accounts as needed and close accounts as needed.",
        "Needed In Advance": "",
        "Evidence Required": "List of active ISR-Live accounts; users to create/remove.",
    },
    {
        "Macro Category": "DiaSorin Accounts Optimization",
        "Item": "RGA Manager",
        "Definition": "Review RGA Manager account access. Open accounts as needed and close accounts as needed.",
        "Needed In Advance": "",
        "Evidence Required": "List of active RGA Manager accounts; users to create/remove; confirmation of trained users.",
    },
    {
        "Macro Category": "Technical Evaluation",
        "Item": "FSEs",
        "Definition": "Perform the FSE evaluation to all FSEs servicing DiaSorin instruments.",
        "Needed In Advance": "Provide the list of FSEs to take the quiz. Complete the quiz before the assessment is done. Recovery session to be done during the assessment.",
        "Evidence Required": "FSE assessment results; attendance list; recovery plan for failed or pending engineers.",
    },
    {
        "Macro Category": "Technical Evaluation",
        "Item": "Lead FSE",
        "Definition": "Perform the lead evaluation to the Lead FSEs.",
        "Needed In Advance": "If an Advanced SS Session does not take place during the visit: provide the list of FSEs to take the quiz, complete the quiz before the assessment and perform recovery session during the assessment.",
        "Evidence Required": "Lead FSE assessment result; advanced session evidence; retraining plan if needed.",
    },
    {
        "Macro Category": "Service Tools",
        "Item": "Lubrication Kits",
        "Definition": "How many kits are available in stock? How many FSEs have a full kit? Define the amount of kits to be ordered.",
        "Needed In Advance": "Number of kits available in stock. Number of kits already provided to FSEs.",
        "Evidence Required": "Tool inventory; photos; kit assignment list by FSE; gap/order list.",
    },
    {
        "Macro Category": "Service Tools",
        "Item": "System Dedicated Tools",
        "Definition": "How many sets of tools are available in stock? How many FSEs have a full set depending on systems available in the country? Define amount of sets to be ordered.",
        "Needed In Advance": "",
        "Evidence Required": "Dedicated tool inventory by platform; photos; FSE assignment list; gap/order list.",
    },
    {
        "Macro Category": "Service Tools",
        "Item": "Service Tools",
        "Definition": "Evaluate the type of tools used by FSEs. Verify if they have all tools needed to service the systems, including screwdrivers, allen keys, metric/standard tools, etc.",
        "Needed In Advance": "",
        "Evidence Required": "General tool inventory; photos; missing tools list; corrective plan.",
    },
    {
        "Macro Category": "Service Tools",
        "Item": "Bomgar",
        "Definition": "How many systems are connected to Bomgar compared to the whole installed base? Identify missing SN and reason why each system is not connected.",
        "Needed In Advance": "",
        "Evidence Required": "Bomgar/BeyondTrust installed base report; missing SN list; reason and action plan.",
    },
    {
        "Macro Category": "Stock Level",
        "Item": "Data Extraction",
        "Definition": "Evaluate the way stock data is extracted. Evaluate the outcome of the extraction: location, invoice link, quantity, etc.",
        "Needed In Advance": "Get the spare parts stock file for analysis before the assessment is done.",
        "Evidence Required": "Spare parts stock file; extraction method; inventory owner; location and quantity fields.",
    },
    {
        "Macro Category": "Stock Level",
        "Item": "Analysis",
        "Definition": "Compare the current stock versus the stock level the distributor shall maintain.",
        "Needed In Advance": "",
        "Evidence Required": "Stock gap analysis versus carstock/minimum requirement; value using Option 2 when applicable.",
    },
    {
        "Macro Category": "Service Traceability System",
        "Item": "Traceability Tool",
        "Definition": "Does the distributor have a CRM software? Name the software used for traceability of work orders.",
        "Needed In Advance": "",
        "Evidence Required": "Name of CRM/ERP/tool; screenshots or workflow evidence; user/process description.",
    },
    {
        "Macro Category": "Service Traceability System",
        "Item": "Service Order Categorization",
        "Definition": "Are work orders categorized by the distributor? Are categories compatible with DiaSorin categories? Evaluate possibility to harmonize categories with DiaSorin.",
        "Needed In Advance": "",
        "Evidence Required": "WO category list; examples; mapping to DiaSorin categories; harmonization action plan.",
    },
    {
        "Macro Category": "Service Traceability System",
        "Item": "Data Extraction",
        "Definition": "Perform data extraction for all field service activities including service interventions and spare part usage, at least last two years if possible. Evaluate if it can be converted into numbers. Calculate KPIs: MTBF, MTBV, SDRR and MTTR. Perform HCI and HSI analysis.",
        "Needed In Advance": "If data can be extracted, complete KPIs file provided by DiaSorin. Provide extraction of all spare parts used in each system with SP PN, replacement date and analyzer SN. If WO are categorized via software and extraction is possible, perform HSI analysis.",
        "Evidence Required": "Service activity extraction; SP usage by SN/date/PN; KPI file; HCI/HSI dataset.",
    },
    {
        "Macro Category": "Service Traceability System",
        "Item": "Activity Tracker",
        "Definition": "How does the distributor follow up periodic activities, updates and retrofits? Review completion percentage for ongoing and expired retrofits and software updates. Place POs for pending retrofits. Define action plan for software updates.",
        "Needed In Advance": "",
        "Evidence Required": "Retrofit/SW update tracker; completion percentage; pending PO list; action plan.",
    },
    {
        "Macro Category": "Customer Visit",
        "Item": "Customer 1",
        "Definition": "Visit a customer where the PM has been performed in the instrument in the last 3 months, preferably LIAISON XL.",
        "Needed In Advance": "",
        "Evidence Required": "Visit report; photos; PM evidence; instrument SN; findings and action plan.",
    },
    {
        "Macro Category": "Customer Visit",
        "Item": "Customer 2",
        "Definition": "VIP customer visit.",
        "Needed In Advance": "",
        "Evidence Required": "Visit report; photos; customer feedback; instrument SN; pending actions.",
    },
    {
        "Macro Category": "Customer Visit",
        "Item": "Customer 3",
        "Definition": "Visit the system with the highest number of failures.",
        "Needed In Advance": "",
        "Evidence Required": "Failure history; troubleshooting evidence; visit report; corrective action plan.",
    },
]

RESPONSE_SCORE_MAP = {
    "Y - Cumple": 1.0,
    "P - Parcial": 0.5,
    "N - No cumple": 0.0,
    "NA - No aplica": np.nan,
}


def init_corporate_db() -> None:
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS corporate_assessments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, distributor TEXT,
        country TEXT, period TEXT, reviewer TEXT, overall_score REAL, maturity TEXT,
        summary_json TEXT, notes TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS corporate_assessment_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, assessment_id INTEGER, macro_category TEXT, item TEXT,
        definition TEXT, needed_in_advance TEXT, evidence_required TEXT, response TEXT,
        score REAL, weight REAL, weighted_score REAL, risk TEXT, responsible TEXT,
        due_date TEXT, evidence_uploaded TEXT, item_status TEXT, comments TEXT, action_plan TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS corporate_evidence (
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, assessment_id INTEGER,
        macro_category TEXT, item TEXT, filename TEXT, stored_path TEXT, file_type TEXT, file_size INTEGER,
        notes TEXT)""")
    conn.commit(); conn.close()


def corporate_template_df() -> pd.DataFrame:
    df = pd.DataFrame(DEFAULT_CORPORATE_ITEMS)
    counts = df["Macro Category"].value_counts().to_dict()
    df["Response"] = "N - No cumple"
    df["Score"] = 0.0
    df["Category Weight"] = df["Macro Category"].map(CORPORATE_CATEGORY_WEIGHTS).fillna(0).astype(float)
    df["Item Weight"] = df.apply(lambda r: round(float(r["Category Weight"]) / counts.get(r["Macro Category"], 1), 4), axis=1)
    df["Weighted Score"] = 0.0
    df["Risk"] = "Medium"
    df["Responsible"] = ""
    df["Due Date"] = ""
    df["Evidence Uploaded"] = "No"
    df["Item Status"] = "Open"
    df["Comments / Notes"] = ""
    df["Action Plan"] = ""
    return recalc_corporate_scores(df)


def recalc_corporate_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "Response" not in out.columns:
        out["Response"] = "N - No cumple"
    out["Score"] = out["Response"].map(RESPONSE_SCORE_MAP)
    out["Weighted Score"] = out.apply(
        lambda r: 0.0 if pd.isna(r.get("Score")) else round(float(r.get("Score", 0)) * float(r.get("Item Weight", 0)), 4), axis=1
    )
    # Riesgo sugerido, manteniendo riesgo manual si existe y es válido.
    def auto_status(resp):
        if resp == "Y - Cumple": return "Closed"
        if resp == "P - Parcial": return "In Progress"
        if resp == "NA - No aplica": return "Not Applicable"
        return "Open"
    if "Item Status" not in out.columns:
        out["Item Status"] = out["Response"].apply(auto_status)
    return out


def corporate_summary(df: pd.DataFrame) -> Dict:
    if df is None or df.empty:
        return {"overall_score": 0.0, "maturity": "Sin datos", "open_items": 0, "critical_items": 0}
    work = recalc_corporate_scores(df)
    applicable = work[work["Response"] != "NA - No aplica"].copy()
    possible = float(applicable["Item Weight"].sum()) if not applicable.empty else 0.0
    earned = float(applicable["Weighted Score"].sum()) if not applicable.empty else 0.0
    overall = round((earned / possible) * 100, 1) if possible else 0.0
    open_items = int((work["Response"].isin(["N - No cumple", "P - Parcial"])).sum())
    critical_items = int((work.get("Risk", pd.Series(dtype=str)).astype(str) == "Critical").sum())
    if overall >= 90 and critical_items == 0:
        maturity = "Mature / Controlled"
    elif overall >= 75:
        maturity = "Controlled with action plan"
    elif overall >= 60:
        maturity = "Partial / Relevant gaps"
    else:
        maturity = "Critical / High operational risk"
    by_cat = []
    for cat, g in work.groupby("Macro Category", dropna=False):
        g_app = g[g["Response"] != "NA - No aplica"]
        p = float(g_app["Item Weight"].sum()) if not g_app.empty else 0.0
        e = float(g_app["Weighted Score"].sum()) if not g_app.empty else 0.0
        by_cat.append({"Macro Category": cat, "Score": round((e / p) * 100, 1) if p else 0.0, "Items": len(g), "Open/Partial": int(g["Response"].isin(["N - No cumple", "P - Parcial"]).sum())})
    return {"overall_score": overall, "maturity": maturity, "open_items": open_items, "critical_items": critical_items, "by_category": by_cat}


def apply_isrlive_to_corporate(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    summary = st.session_state.get("current_summary") or {}
    result = st.session_state.get("current_result")
    if not summary or result is None or result.empty:
        return out

    def set_item(category, item, response, comment):
        mask = (out["Macro Category"] == category) & (out["Item"] == item)
        if mask.any():
            out.loc[mask, "Response"] = response
            existing = out.loc[mask, "Comments / Notes"].astype(str).fillna("")
            out.loc[mask, "Comments / Notes"] = existing.apply(lambda x: (x + " | " if x else "") + comment)

    active = int(summary.get("active", 0))
    mc_missing = int(summary.get("machine_config_missing", 0))
    data_missing = int(summary.get("data_quality_not_ok", 0))
    sw_not_ok = int(summary.get("software_not_ok", 0))

    if active > 0:
        set_item("Installed Base Certification", "System Configuration", "Y - Cumple" if mc_missing == 0 else "P - Parcial", f"Auto ISR-Live: {mc_missing} active instruments with Machine Configuration pending/invalid.")
        set_item("Installed Base Certification", "Customer Data", "Y - Cumple" if data_missing == 0 else "P - Parcial", f"Auto ISR-Live: {data_missing} active instruments with basic customer/status data gaps.")
        set_item("Installed Base Certification", "System Status", "Y - Cumple", f"Auto ISR-Live: {active} active instruments evaluated with operational status present in export.")
        set_item("Installed Base Certification", "Installed Base Update", "P - Parcial", "Auto ISR-Live: export loaded. Signed certification letter must still be attached/validated.")
        set_item("Service Tools", "Bomgar", "P - Parcial", "Pending automatic Bomgar coverage validation. Upload BeyondTrust/Bomgar report or complete manually.")
        if sw_not_ok == 0:
            set_item("Service Traceability System", "Activity Tracker", "P - Parcial", "Auto ISR-Live: no software gap detected by current version rules; retrofit/update tracker still requires manual evidence.")
    return recalc_corporate_scores(out)


def save_corporate_assessment(df: pd.DataFrame, meta: Dict) -> int:
    work = recalc_corporate_scores(df)
    summary = corporate_summary(work)
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO corporate_assessments (created_at, distributor, country, period,
        reviewer, overall_score, maturity, summary_json, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now_str(), meta.get("distributor", ""), meta.get("country", ""), meta.get("period", ""), meta.get("reviewer", ""),
         float(summary.get("overall_score", 0)), summary.get("maturity", ""), json.dumps(summary, ensure_ascii=False), meta.get("notes", "")))
    aid = cur.lastrowid
    for _, r in work.iterrows():
        cur.execute("""INSERT INTO corporate_assessment_items (assessment_id, macro_category, item,
            definition, needed_in_advance, evidence_required, response, score, weight, weighted_score,
            risk, responsible, due_date, evidence_uploaded, item_status, comments, action_plan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (aid, r.get("Macro Category", ""), r.get("Item", ""), r.get("Definition", ""), r.get("Needed In Advance", ""),
             r.get("Evidence Required", ""), r.get("Response", ""), None if pd.isna(r.get("Score")) else float(r.get("Score", 0)),
             float(r.get("Item Weight", 0)), float(r.get("Weighted Score", 0)), r.get("Risk", ""), r.get("Responsible", ""),
             str(r.get("Due Date", "")), r.get("Evidence Uploaded", ""), r.get("Item Status", ""), r.get("Comments / Notes", ""), r.get("Action Plan", "")))
    conn.commit(); conn.close(); return int(aid)


def load_corporate_history(limit: int = 50) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("""SELECT id, created_at, distributor, country, period, reviewer,
        overall_score, maturity FROM corporate_assessments ORDER BY id DESC LIMIT ?""", conn, params=(limit,))
    conn.close(); return df


def load_corporate_items(assessment_id: int) -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("""SELECT macro_category AS 'Macro Category', item AS 'Item', definition AS 'Definition',
        needed_in_advance AS 'Needed In Advance', evidence_required AS 'Evidence Required', response AS 'Response',
        score AS 'Score', weight AS 'Item Weight', weighted_score AS 'Weighted Score', risk AS 'Risk', responsible AS 'Responsible',
        due_date AS 'Due Date', evidence_uploaded AS 'Evidence Uploaded', item_status AS 'Item Status', comments AS 'Comments / Notes',
        action_plan AS 'Action Plan' FROM corporate_assessment_items WHERE assessment_id = ? ORDER BY id""", conn, params=(assessment_id,))
    conn.close(); return df


def save_corporate_item_evidence(assessment_id: Optional[int], macro_category: str, item: str, uploaded_file, notes: str = "") -> None:
    folder = EVIDENCE_DIR / "corporate_assessment" / safe_filename(str(assessment_id or "draft")) / safe_filename(macro_category) / safe_filename(item)
    folder.mkdir(parents=True, exist_ok=True)
    content = bytes(uploaded_file.getbuffer())
    stored_path = folder / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_filename(uploaded_file.name)}"
    stored_path.write_bytes(content)
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""INSERT INTO corporate_evidence (created_at, assessment_id, macro_category, item,
        filename, stored_path, file_type, file_size, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (now_str(), assessment_id, macro_category, item, uploaded_file.name, str(stored_path), uploaded_file.type, len(content), notes))
    conn.commit(); conn.close()


def load_corporate_evidence(assessment_id: Optional[int] = None) -> pd.DataFrame:
    conn = get_conn()
    if assessment_id:
        df = pd.read_sql_query("SELECT * FROM corporate_evidence WHERE assessment_id = ? ORDER BY id DESC", conn, params=(assessment_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM corporate_evidence ORDER BY id DESC LIMIT 300", conn)
    conn.close(); return df


def corporate_excel_bytes(df: pd.DataFrame, meta: Dict) -> bytes:
    work = recalc_corporate_scores(df)
    summary = corporate_summary(work)
    by_category = pd.DataFrame(summary.get("by_category", []))
    executive = pd.DataFrame([
        {"Indicator": "Distributor", "Value": meta.get("distributor", "")},
        {"Indicator": "Country", "Value": meta.get("country", "")},
        {"Indicator": "Period", "Value": meta.get("period", "")},
        {"Indicator": "Period Start", "Value": meta.get("period_start", "")},
        {"Indicator": "Period End", "Value": meta.get("period_end", "")},
        {"Indicator": "World Region", "Value": meta.get("world_region", "")},
        {"Indicator": "Commercial Region", "Value": meta.get("commercial_region", "")},
        {"Indicator": "Reviewer", "Value": meta.get("reviewer", "")},
        {"Indicator": "Overall Score", "Value": f"{summary.get('overall_score', 0)}%"},
        {"Indicator": "Maturity", "Value": summary.get("maturity", "")},
        {"Indicator": "Open/Partial Items", "Value": summary.get("open_items", 0)},
        {"Indicator": "Critical Items", "Value": summary.get("critical_items", 0)},
    ])
    return to_excel_bytes({"Executive Summary": executive, "Score by Category": by_category, "Corporate Assessment": work})


def page_corporate_assessment():
    st.subheader("0. Assessment corporativo")
    st.caption("Matriz completa cargada desde el formato corporativo original. Puedes modificar respuestas, notas, responsables, riesgos, fechas y acciones.")

    if "corporate_df" not in st.session_state:
        st.session_state["corporate_df"] = corporate_template_df()
    if "corporate_assessment_id" not in st.session_state:
        st.session_state["corporate_assessment_id"] = None

    with st.expander("Datos generales de la evaluación", expanded=True):
        st.markdown("#### Distribuidor y país")
        distributor, country, world_region, commercial_region = distributor_country_selector(prefix="corporate")

        st.markdown("#### Periodo evaluado")
        period_start, period_end, period = period_selector(prefix="corporate")

        c1, c2 = st.columns([1.2, 2.8])
        reviewer = c1.text_input("Reviewer", value=st.session_state.get("corporate_reviewer", "Javier Avellaneda"))
        notes = c2.text_area("Notas generales", value=st.session_state.get("corporate_notes", ""), height=80)

        st.session_state["corporate_distributor"] = distributor
        st.session_state["corporate_country"] = country
        st.session_state["corporate_period"] = period
        st.session_state["corporate_period_start_label"] = str(period_start)
        st.session_state["corporate_period_end_label"] = str(period_end)
        st.session_state["corporate_world_region"] = world_region
        st.session_state["corporate_commercial_region"] = commercial_region
        st.session_state["corporate_reviewer"] = reviewer
        st.session_state["corporate_notes"] = notes

    b1, b2, b3, b4 = st.columns(4)
    if b1.button("Recargar formato base", use_container_width=True):
        st.session_state["corporate_df"] = corporate_template_df(); st.success("Formato base recargado.")
    if b2.button("Aplicar hallazgos ISR-Live actuales", use_container_width=True):
        st.session_state["corporate_df"] = apply_isrlive_to_corporate(st.session_state["corporate_df"]); st.success("Hallazgos ISR-Live aplicados a los ítems relacionados.")
    if b3.button("Recalcular score", use_container_width=True):
        st.session_state["corporate_df"] = recalc_corporate_scores(st.session_state["corporate_df"]); st.success("Score recalculado.")

    df = recalc_corporate_scores(st.session_state["corporate_df"])
    summary = corporate_summary(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Score corporativo", f"{summary.get('overall_score', 0)}%")
    c2.metric("Madurez", summary.get("maturity", ""))
    c3.metric("Ítems abiertos/parciales", summary.get("open_items", 0))
    c4.metric("Ítems críticos", summary.get("critical_items", 0))

    by_cat = pd.DataFrame(summary.get("by_category", []))
    if not by_cat.empty:
        st.plotly_chart(px.bar(by_cat, x="Macro Category", y="Score", text="Score", hover_data=["Items", "Open/Partial"], title="Score por macro-categoría"), use_container_width=True)

    st.markdown("### Matriz editable")
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Macro Category": st.column_config.TextColumn("Macro Category", disabled=True),
            "Item": st.column_config.TextColumn("Item", disabled=True),
            "Definition": st.column_config.TextColumn("Definition", disabled=True, width="large"),
            "Needed In Advance": st.column_config.TextColumn("Needed In Advance", disabled=True, width="large"),
            "Evidence Required": st.column_config.TextColumn("Evidence Required", width="large"),
            "Response": st.column_config.SelectboxColumn("Response", options=list(RESPONSE_SCORE_MAP.keys()), required=True),
            "Score": st.column_config.NumberColumn("Score", disabled=True, format="%.2f"),
            "Category Weight": st.column_config.NumberColumn("Category Weight", disabled=True, format="%.2f"),
            "Item Weight": st.column_config.NumberColumn("Item Weight", disabled=True, format="%.2f"),
            "Weighted Score": st.column_config.NumberColumn("Weighted Score", disabled=True, format="%.2f"),
            "Risk": st.column_config.SelectboxColumn("Risk", options=["Low", "Medium", "High", "Critical"]),
            "Evidence Uploaded": st.column_config.SelectboxColumn("Evidence Uploaded", options=["No", "Partial", "Yes", "Not required"]),
            "Item Status": st.column_config.SelectboxColumn("Item Status", options=["Open", "In Progress", "Closed", "Overdue", "Not Applicable"]),
            "Due Date": st.column_config.TextColumn("Due Date"),
            "Comments / Notes": st.column_config.TextColumn("Comments / Notes", width="large"),
            "Action Plan": st.column_config.TextColumn("Action Plan", width="large"),
        },
        key="corporate_editor",
    )
    st.session_state["corporate_df"] = recalc_corporate_scores(edited)

    tabs = st.tabs(["Plan de acción", "Evidencia por ítem", "Guardar / exportar", "Histórico"])
    with tabs[0]:
        action_df = st.session_state["corporate_df"][st.session_state["corporate_df"]["Response"].isin(["N - No cumple", "P - Parcial"])].copy()
        action_df = action_df[["Macro Category", "Item", "Risk", "Responsible", "Due Date", "Evidence Required", "Comments / Notes", "Action Plan", "Item Status"]]
        st.dataframe(action_df, use_container_width=True, hide_index=True)
    with tabs[1]:
        st.markdown("#### Cargar evidencia asociada a un punto del assessment")
        cats = list(st.session_state["corporate_df"]["Macro Category"].dropna().unique())
        selected_cat = st.selectbox("Macro Category", cats)
        items = list(st.session_state["corporate_df"].loc[st.session_state["corporate_df"]["Macro Category"] == selected_cat, "Item"].dropna().unique())
        selected_item = st.selectbox("Item", items)
        evidence_notes = st.text_area("Nota de evidencia", height=70)
        files = st.file_uploader("Subir evidencia del punto seleccionado", type=["png","jpg","jpeg","pdf","xlsx","xls","csv","txt","zip","docx","pptx"], accept_multiple_files=True, key="corporate_item_evidence")
        if st.button("Guardar evidencia del ítem", type="primary"):
            if not files:
                st.warning("Carga al menos un archivo.")
            else:
                aid = st.session_state.get("corporate_assessment_id")
                for f in files:
                    save_corporate_item_evidence(aid, selected_cat, selected_item, f, evidence_notes)
                mask = (st.session_state["corporate_df"]["Macro Category"] == selected_cat) & (st.session_state["corporate_df"]["Item"] == selected_item)
                st.session_state["corporate_df"].loc[mask, "Evidence Uploaded"] = "Yes"
                st.success("Evidencia guardada y punto marcado como evidencia cargada.")
        ev = load_corporate_evidence(st.session_state.get("corporate_assessment_id"))
        if not ev.empty:
            st.dataframe(ev[["created_at","macro_category","item","filename","notes","stored_path"]], use_container_width=True, hide_index=True)
    with tabs[2]:
        meta = {
            "distributor": distributor,
            "country": country,
            "period": period,
            "period_start": st.session_state.get("corporate_period_start_label", ""),
            "period_end": st.session_state.get("corporate_period_end_label", ""),
            "world_region": st.session_state.get("corporate_world_region", ""),
            "commercial_region": st.session_state.get("corporate_commercial_region", ""),
            "reviewer": reviewer,
            "notes": notes,
        }
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Guardar assessment corporativo", type="primary", use_container_width=True):
                aid = save_corporate_assessment(st.session_state["corporate_df"], meta)
                st.session_state["corporate_assessment_id"] = aid
                st.success(f"Assessment corporativo guardado. ID interno: {aid}")
        with col2:
            st.download_button("Descargar assessment corporativo Excel", data=corporate_excel_bytes(st.session_state["corporate_df"], meta), file_name=f"Corporate_Service_Assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    with tabs[3]:
        hist = load_corporate_history(100)
        st.caption("Histórico de assessments corporativos guardados.")
        if hist.empty:
            st.info("Todavía no hay registros guardados.")
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True)
            selected_id = st.number_input("Cargar ID guardado", min_value=1, value=int(hist.iloc[0]["id"]))
            if st.button("Cargar assessment guardado"):
                loaded = load_corporate_items(int(selected_id))
                if loaded.empty:
                    st.warning("No encontré ítems para ese ID.")
                else:
                    # Restaurar columnas de peso de categoría para visualización.
                    loaded["Category Weight"] = loaded["Macro Category"].map(CORPORATE_CATEGORY_WEIGHTS).fillna(0).astype(float)
                    st.session_state["corporate_df"] = recalc_corporate_scores(loaded)
                    st.session_state["corporate_assessment_id"] = int(selected_id)
                    st.success(f"Assessment {selected_id} cargado.")

def page_isrlive():
    st.subheader("1. Evaluación ISR-Live"); st.write("Carga el CSV o Excel descargado directamente desde ISR-Live.")
    target_sw = sidebar_config(); only_active = st.toggle("Evaluar únicamente instrumentos activos / en rutina", value=True)
    uploaded = st.file_uploader("Subir archivo ISR-Live", type=["csv","xlsx","xls"], accept_multiple_files=False)
    if not uploaded:
        st.info("Sube un archivo para iniciar la evaluación."); hist = load_history()
        if not hist.empty: st.markdown("### Histórico de evaluaciones guardadas"); st.dataframe(hist, use_container_width=True, hide_index=True)
        return
    try: raw_df = read_table(uploaded)
    except Exception as exc: st.error(f"No pude leer el archivo: {exc}"); return
    if raw_df.empty: st.warning("El archivo está vacío."); return
    result, summary, mapping = evaluate(raw_df, target_sw, only_active=only_active); plan = action_plan(result)
    st.session_state["current_result"] = result; st.session_state["current_summary"] = summary; st.session_state["current_plan"] = plan; st.session_state["current_raw"] = raw_df; st.session_state["current_filename"] = uploaded.name
    render_metrics(summary); render_charts(result)
    tabs = st.tabs(["Resultados", "Plan de acción", "Columnas detectadas", "Datos originales", "Guardar / Exportar"])
    with tabs[0]: st.dataframe(display_result_df(result), use_container_width=True, hide_index=True)
    with tabs[1]: st.success("No se generaron acciones abiertas con las reglas actuales.") if plan.empty else st.dataframe(plan, use_container_width=True, hide_index=True)
    with tabs[2]: st.dataframe(pd.DataFrame([{"Campo esperado": k, "Columna detectada": v or "No detectada"} for k,v in mapping.items()]), use_container_width=True, hide_index=True)
    with tabs[3]: st.dataframe(raw_df, use_container_width=True, hide_index=True)
    with tabs[4]:
        col1,col2 = st.columns(2)
        with col1:
            if st.button("Guardar evaluación en base local", type="primary"):
                aid = save_assessment(result, summary, uploaded.name); st.session_state["assessment_id"] = aid; st.success(f"Evaluación guardada. ID interno: {aid}")
        with col2:
            excel = to_excel_bytes({"Assessment Results": display_result_df(result), "Action Plan": plan, "Raw ISR-Live": raw_df})
            st.download_button("Descargar Excel", data=excel, file_name=f"Service_Assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if REPORTLAB_OK:
            pdf = make_pdf_report(result, summary, plan); st.download_button("Descargar PDF ejecutivo", data=pdf, file_name=f"Service_Assessment_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", mime="application/pdf")
        else: st.warning("Para PDF instala reportlab. Ya está incluido en requirements.txt.")

def evidence_form(sn: str):
    st.markdown("### Evidencia de visita técnica")
    with st.form("evidence_form", clear_on_submit=False):
        c1,c2,c3 = st.columns(3); visit_date = c1.date_input("Fecha de visita", value=date.today()); visit_type = c2.selectbox("Tipo de visita", ["Technical review", "Preventive maintenance", "Corrective maintenance", "Training", "Installation", "Follow-up", "Other"]); risk = c3.selectbox("Riesgo observado", ["Low", "Medium", "High", "Critical"])
        c4,c5 = st.columns(2); engineer = c4.text_input("Ingeniero / responsable"); customer_contact = c5.text_input("Contacto del cliente")
        summary = st.text_area("Resumen de la visita", height=90); conclusion = st.text_area("Conclusión técnica", height=90); next_action = st.text_area("Próxima acción / compromiso", height=80)
        files = st.file_uploader("Cargar fotos, PDF, screenshots, reportes, Excel o ZIP", type=["png","jpg","jpeg","pdf","xlsx","xls","csv","txt","zip","docx"], accept_multiple_files=True)
        submitted = st.form_submit_button("Guardar evidencia", type="primary")
    if submitted:
        if not files: st.warning("Carga al menos un archivo."); return
        fields = {"visit_date": str(visit_date), "visit_type": visit_type, "engineer": engineer, "customer_contact": customer_contact, "risk": risk, "summary": summary, "conclusion": conclusion, "next_action": next_action}
        for f in files: save_evidence(sn, fields, f)
        st.success(f"Evidencia guardada para SN {sn}.")
    ev = load_evidence(sn)
    if not ev.empty:
        st.markdown("### Evidencia registrada"); st.dataframe(ev[["created_at","visit_date","visit_type","engineer","risk","filename","summary","next_action"]], use_container_width=True, hide_index=True)
        imgs=[]
        for _, r in ev.iterrows():
            p = Path(str(r.get("stored_path", "")))
            if p.exists() and p.suffix.lower() in [".jpg", ".jpeg", ".png"]: imgs.append(p)
        if imgs:
            with st.expander("Vista rápida de imágenes"):
                cols=st.columns(3)
                for i,p in enumerate(imgs[:12]):
                    with cols[i%3]: st.image(str(p), caption=p.name, use_container_width=True)

def troubleshooting_form(sn: str):
    st.markdown("### Troubleshooting / TempArchive")
    uploaded = st.file_uploader("Subir ZIP, LogFile, ErrorFile o archivo de texto", type=["zip","txt","log","csv","xml"], accept_multiple_files=False, key="trouble_file")
    if not uploaded: return
    analysis = analyze_troubleshooting_file(uploaded); c1,c2,c3 = st.columns(3); c1.metric("Archivos leídos", analysis.get("total_files",0)); c2.metric("Líneas analizadas", analysis.get("total_lines",0)); c3.metric("Hits relevantes", analysis.get("total_hits",0))
    cats = analysis.get("categories", {})
    if cats:
        df_cats = pd.DataFrame([{"Categoría":k,"Eventos":v} for k,v in cats.items()]).sort_values("Eventos", ascending=False); st.plotly_chart(px.bar(df_cats, x="Categoría", y="Eventos", text="Eventos", title="Patrones identificados"), use_container_width=True)
    else: st.info("No se detectaron patrones con las reglas base.")
    st.markdown("### Recomendación inicial"); st.write(analysis.get("recommendation", ""))
    highlights = pd.DataFrame(analysis.get("highlights", []))
    if not highlights.empty:
        st.markdown("### Líneas relevantes"); st.dataframe(highlights, use_container_width=True, hide_index=True); st.download_button("Descargar líneas relevantes CSV", data=highlights.to_csv(index=False).encode("utf-8-sig"), file_name=f"Troubleshooting_Highlights_{sn}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv")
    if st.button("Guardar análisis de troubleshooting", type="primary"):
        save_troubleshooting(sn, uploaded.name, analysis); st.success("Análisis guardado.")

def page_workspace():
    st.subheader("2. Instrument Workspace"); st.write("Selecciona un instrumento por serial number y carga evidencia o troubleshooting.")
    result = st.session_state.get("current_result")
    if result is None or result.empty: st.info("Primero carga un archivo ISR-Live en la pestaña de evaluación."); return
    serials = sorted([x for x in result["serial_number"].dropna().astype(str).unique() if x])
    if not serials: st.warning("No encontré serial numbers en el archivo."); return
    sn = st.selectbox("Serial Number", serials); row = result[result["serial_number"].astype(str) == str(sn)].head(1)
    if not row.empty:
        r=row.iloc[0]; c1,c2,c3,c4=st.columns(4); c1.metric("Instrumento", r.get("instrument_type","")); c2.metric("Cliente", r.get("customer_name","")); c3.metric("Score", r.get("score","")); c4.metric("Riesgo", r.get("risk",""))
        with st.expander("Hallazgos actuales", expanded=True):
            for f in r.get("findings", []): st.write(f"- {f}")
    tabs = st.tabs(["Cargar evidencia", "Analizar troubleshooting", "Histórico del serial"])
    with tabs[0]: evidence_form(sn)
    with tabs[1]: troubleshooting_form(sn)
    with tabs[2]:
        st.markdown("### Evidencia"); ev = load_evidence(sn); st.caption("Sin evidencia registrada.") if ev.empty else st.dataframe(ev, use_container_width=True, hide_index=True)
        st.markdown("### Troubleshooting"); tr = load_troubleshooting(sn); st.caption("Sin análisis registrado.") if tr.empty else st.dataframe(tr, use_container_width=True, hide_index=True)

def executive_summary(summary: Dict) -> str:
    score=summary.get("global_score",0); active=summary.get("active",0); critical=summary.get("critical",0); mc=summary.get("machine_config_missing",0); sw=summary.get("software_not_ok",0)
    maturity = "maduro y controlado" if score>=90 and critical==0 else "controlado con acciones pendientes" if score>=75 else "parcial, con brechas relevantes" if score>=60 else "crítico, con riesgo operativo alto"
    return f"Durante la revisión técnica se evaluaron {active} instrumentos activos con base en la información exportada desde ISR-Live. El score global obtenido fue {score}%, clasificando el estado general del soporte como {maturity}.\n\nLos principales focos de atención son: {mc} instrumentos con Machine Configuration incompleta o inválida, {sw} instrumentos con software por debajo de la versión objetivo configurada y {critical} riesgos críticos abiertos.\n\nSe recomienda ejecutar el plan de acción generado por la app, priorizando actualización de datos en ISR-Live, corrección de Machine Configuration, actualización de software cuando aplique y carga de evidencia documental por serial number."

def page_report():
    st.subheader("3. Informe consolidado"); result = st.session_state.get("current_result"); summary = st.session_state.get("current_summary"); plan = st.session_state.get("current_plan")
    if result is None or result.empty or summary is None: st.info("Primero carga una evaluación ISR-Live."); return
    st.text_area("Resumen ejecutivo sugerido", value=executive_summary(summary), height=230); ev=load_evidence(); tr=load_troubleshooting(); c1,c2=st.columns(2); c1.metric("Evidencias cargadas", len(ev)); c2.metric("Análisis troubleshooting", len(tr))
    excel=to_excel_bytes({"Assessment Results": display_result_df(result), "Action Plan": plan if plan is not None else pd.DataFrame(), "Evidence Log": ev, "Troubleshooting": tr}); st.download_button("Descargar Excel consolidado", data=excel, file_name=f"Consolidated_Service_Assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if REPORTLAB_OK:
        pdf=make_pdf_report(result, summary, plan if plan is not None else pd.DataFrame()); st.download_button("Descargar PDF ejecutivo", data=pdf, file_name=f"Executive_Service_Assessment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf", mime="application/pdf")

def page_config():
    st.subheader("4. Configuración")
    st.write(f"Carpeta de la app: `{BASE_DIR}`")
    st.write(f"Base de datos: `{DB_PATH}`")
    st.write(f"Carpeta de evidencias: `{EVIDENCE_DIR}`")
    st.write(f"Maestro de distribuidores: `{DISTRIBUTOR_MASTER_PATH}`")

    st.markdown("### Maestro de distribuidores")
    master = load_distributor_master(latam_only=False)
    if master.empty:
        st.warning("No encontré data/distributors_master.csv. Puedes reemplazarlo por un nuevo export de Records_List_Report.")
    else:
        st.caption(f"{master['Distributor'].nunique()} distribuidores únicos · {master['Country'].nunique()} países únicos.")
        st.dataframe(master, use_container_width=True, hide_index=True)

    st.markdown("### Histórico")
    hist=load_history(100)
    st.caption("Sin evaluaciones guardadas.") if hist.empty else st.dataframe(hist, use_container_width=True, hide_index=True)

    st.markdown("### Valores inválidos para Machine Configuration")
    st.dataframe(pd.DataFrame({"Valor inválido": sorted(INVALID_CONFIG_VALUES)}), use_container_width=True, hide_index=True)

    st.markdown("### GitHub")
    st.code("""
git init
git add .
git commit -m "Initial LATAM Service Assessment app"
git branch -M main
git remote add origin https://github.com/TU-USUARIO/TU-REPOSITORIO.git
git push -u origin main
    """.strip(), language="bash")

def main():
    st.set_page_config(page_title="LATAM Service Assessment", page_icon="🧪", layout="wide"); init_db(); init_corporate_db(); css(); header()
    page = st.sidebar.radio("Navegación", ["Assessment corporativo", "Evaluación ISR-Live", "Instrument Workspace", "Informe consolidado", "Configuración"])
    if page == "Assessment corporativo": page_corporate_assessment()
    elif page == "Evaluación ISR-Live": page_isrlive()
    elif page == "Instrument Workspace": page_workspace()
    elif page == "Informe consolidado": page_report()
    elif page == "Configuración": page_config()

if __name__ == "__main__":
    main()
