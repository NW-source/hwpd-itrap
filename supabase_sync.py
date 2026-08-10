"""
supabase_sync.py — HWPD i-Trap Cloud Sync Facade
ตอนนี้ route ทุก call ไปยัง db_adapter.py (PostgreSQL บน Oracle Cloud)
คงชื่อฟังก์ชันเดิมทุกตัวเพื่อ backward-compatible กับ cloud_app.py และ app.py
"""
import streamlit as st
import pandas as pd
from typing import Optional
from datetime import datetime

# ─── Import PostgreSQL adapter ────────────────────────────────────────────────
from db_adapter import (
    is_pg_configured,
    push_parquet_local, pull_parquet_local, list_parquet_dates,
    push_daily_report_pg, pull_available_dates_pg, pull_daily_report_pg, pull_all_reports_pg,
    push_realtime_pg, pull_realtime_pg,
    push_historical_suspects_pg, pull_historical_suspects_pg,
    pull_whitelist_pg, pull_whitelist_df_pg, push_whitelist_plate_pg, delete_whitelist_plate_pg,
    log_upload_pg, pull_upload_log_pg,
    push_ai_feedback_pg, pull_ai_feedback_pg,
    push_target_status_pg, pull_target_status_pg, pull_target_status_df_pg,
    check_ip_blocked_pg, update_ip_attempts_pg,
    get_user_pg, get_all_users_pg, create_user_pg, update_user_password_pg, deactivate_user_pg,
)

# ─── Legacy Compat: ฟังก์ชันเหล่านี้ถูกเรียกจาก cloud_app.py / app.py ──────────

def is_supabase_configured() -> bool:
    """ตรวจสอบการเชื่อมต่อ — ตอนนี้ตรวจ PostgreSQL แทน"""
    return is_pg_configured()

@st.cache_resource(show_spinner=False)
def get_supabase_client():
    """DEPRECATED — คืน None เสมอ (ไม่ใช้ Supabase อีกต่อไป)"""
    return None

# ─── PUSH Functions ───────────────────────────────────────────────────────────
def push_daily_report(report_date: str, priority_df: pd.DataFrame,
                       metrics: dict, uploaded_by: str, record_count: int = 0) -> bool:
    return push_daily_report_pg(report_date, priority_df, metrics, uploaded_by, record_count)

def push_realtime_session(session_date: str, priority_df: pd.DataFrame,
                           upload_count: int, first_time: str, last_time: str,
                           uploaded_by: str, record_count: int = 0) -> bool:
    return push_realtime_pg(session_date, priority_df, upload_count, first_time, last_time, uploaded_by, record_count)

def push_suspects(suspects_df: pd.DataFrame) -> bool:
    return push_historical_suspects_pg(suspects_df)

def log_upload(username: str, display_name: str, filename: str,
               report_date: str, record_count: int) -> bool:
    return log_upload_pg(username, display_name, filename, report_date, record_count)

def push_parquet_to_cloud(report_date: str, df_polars, keep_days: int = 30) -> bool:
    """บันทึก Parquet ลง Local Disk (แทน Supabase Storage)"""
    ok = push_parquet_local(report_date, df_polars)
    # cleanup old files > keep_days
    if ok:
        try:
            from datetime import timedelta
            cutoff = (datetime.strptime(report_date, '%Y-%m-%d') - timedelta(days=keep_days)).strftime('%Y-%m-%d')
            import os, db_adapter as _da
            for f in os.listdir(_da.PARQUET_BASE):
                date_str = f.replace('.parquet', '')
                if f.endswith('.parquet') and date_str < cutoff:
                    try:
                        os.remove(os.path.join(_da.PARQUET_BASE, f))
                    except Exception:
                        pass
        except Exception:
            pass
    return ok

def pull_parquet_from_cloud(report_date: str):
    """โหลด Parquet จาก Local Disk (แทน Supabase Storage)"""
    return pull_parquet_local(report_date)

# ─── Whitelist ────────────────────────────────────────────────────────────────
def pull_whitelist() -> set:
    return pull_whitelist_pg()

def pull_whitelist_df() -> pd.DataFrame:
    return pull_whitelist_df_pg()

def push_whitelist_plate(plate: str, note: str = '', added_by: str = 'admin') -> bool:
    return push_whitelist_plate_pg(plate, note, added_by)

def delete_whitelist_plate(plate: str) -> bool:
    return delete_whitelist_plate_pg(plate)

# ─── Historical Suspects ──────────────────────────────────────────────────────
def push_historical_suspects(hs_df: pd.DataFrame) -> bool:
    return push_historical_suspects_pg(hs_df)

def pull_historical_suspects(limit: int = 500) -> pd.DataFrame:
    return pull_historical_suspects_pg(limit)

# ─── Target Status ────────────────────────────────────────────────────────────
def push_target_status(target_id: str, status: str, updated_by: str = 'admin') -> bool:
    return push_target_status_pg(target_id, status, updated_by)

def pull_target_status(target_id: str) -> str:
    return pull_target_status_pg(target_id)

def pull_target_status_df() -> pd.DataFrame:
    return pull_target_status_df_pg()

# ─── PULL Functions ───────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def pull_available_dates() -> list:
    return pull_available_dates_pg()

@st.cache_data(ttl=60, show_spinner=False)
def pull_daily_report(report_date: str) -> dict:
    p_raw, m_raw = pull_daily_report_pg(report_date)
    if p_raw is not None:
        import json
        p_data = json.loads(p_raw) if isinstance(p_raw, str) else p_raw
        return {
            'priority_df':  pd.DataFrame(p_data),
            'metrics':      m_raw or {},
            'uploaded_by':  None,
            'record_count': 0
        }
    return {'priority_df': pd.DataFrame(), 'metrics': {}, 'uploaded_by': None, 'record_count': 0}

@st.cache_data(ttl=30, show_spinner=False)
def pull_realtime(session_date: str) -> Optional[dict]:
    return pull_realtime_pg(session_date)

@st.cache_data(ttl=300, show_spinner=False)
def pull_suspects(limit: int = 200) -> pd.DataFrame:
    return pull_historical_suspects_pg(limit)

@st.cache_data(ttl=60, show_spinner=False)
def pull_upload_log(limit: int = 50) -> pd.DataFrame:
    return pull_upload_log_pg(limit)

# ─── Sync Status (แสดงสถานะใน Sidebar) ──────────────────────────────────────
def show_sync_status():
    try:
        ok = is_pg_configured()
        if ok:
            st.sidebar.caption("🐘 PostgreSQL: พร้อม")
        else:
            st.sidebar.warning("⚠️ PostgreSQL: ไม่ได้เชื่อมต่อ")
    except Exception:
        st.sidebar.caption("🐘 PostgreSQL: N/A")
