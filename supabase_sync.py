"""
supabase_sync.py — Sync ผลลัพธ์ระหว่าง Local ↔ Supabase Cloud
"""
import streamlit as st
import pandas as pd
import json
from datetime import datetime
from typing import Optional

# ─── Connection ───────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def get_supabase_client():
    """สร้าง Supabase client (cached — สร้างครั้งเดียว)"""
    from supabase import create_client
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

def is_supabase_configured() -> bool:
    """ตรวจว่า Supabase ตั้งค่าไว้ไหม"""
    try:
        return bool(st.secrets.get("supabase", {}).get("url"))
    except Exception:
        return False

# ─── PUSH Functions (Local → Supabase) ────────────────────────────────────────
def push_daily_report(report_date: str, priority_df: pd.DataFrame,
                       metrics: dict, uploaded_by: str, record_count: int = 0) -> bool:
    """Push ผลวิเคราะห์รายวันขึ้น Supabase"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        priority_json = priority_df.to_dict('records') if not priority_df.empty else []
        client.table('cloud_daily_reports').upsert({
            'report_date':       report_date,
            'priority_data':     priority_json,
            'dashboard_metrics': metrics,
            'uploaded_by':       uploaded_by,
            'record_count':      record_count,
            'created_at':        datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = str(e)
        return False

def push_realtime_session(session_date: str, priority_df: pd.DataFrame,
                           upload_count: int, first_time: str, last_time: str,
                           uploaded_by: str, record_count: int = 0) -> bool:
    """Push ผล Realtime ขึ้น Supabase"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        priority_json = priority_df.to_dict('records') if not priority_df.empty else []
        client.table('cloud_realtime').upsert({
            'session_date':      session_date,
            'priority_json':     priority_json,
            'upload_count':      upload_count,
            'first_record_time': first_time,
            'last_record_time':  last_time,
            'record_count':      record_count,
            'uploaded_by':       uploaded_by,
            'updated_at':        datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = str(e)
        return False

def push_suspects(suspects_df: pd.DataFrame) -> bool:
    """Push รถวิ่งซ้ำ (Repeat Offenders) ขึ้น Supabase"""
    if not is_supabase_configured() or suspects_df.empty:
        return False
    try:
        client = get_supabase_client()
        records = suspects_df.to_dict('records')
        # upsert ทีละ 100 records
        for i in range(0, len(records), 100):
            batch = records[i:i+100]
            client.table('cloud_suspects').upsert(batch).execute()
        return True
    except Exception as e:
        st.session_state['_sync_error'] = str(e)
        return False

def log_upload(username: str, display_name: str, filename: str,
               report_date: str, record_count: int) -> bool:
    """บันทึกประวัติการ Upload"""
    if not is_supabase_configured():
        return False
    try:
        client = get_supabase_client()
        client.table('upload_log').insert({
            'username':     username,
            'display_name': display_name,
            'filename':     filename,
            'report_date':  report_date,
            'record_count': record_count,
            'uploaded_at':  datetime.now().isoformat()
        }).execute()
        return True
    except Exception:
        return False

# ─── PULL Functions (Supabase → Display) ──────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def pull_available_dates() -> list:
    """ดึงรายการวันที่มีรายงาน"""
    try:
        client = get_supabase_client()
        result = client.table('cloud_daily_reports').select('report_date').order('report_date', desc=True).execute()
        return [r['report_date'] for r in (result.data or [])]
    except Exception:
        return []

@st.cache_data(ttl=60, show_spinner=False)
def pull_daily_report(report_date: str) -> dict:
    """ดึงผลวิเคราะห์รายวัน"""
    try:
        client = get_supabase_client()
        result = client.table('cloud_daily_reports').select('*').eq('report_date', report_date).execute()
        if result.data:
            row = result.data[0]
            priority_df = pd.DataFrame(row.get('priority_data') or [])
            metrics = row.get('dashboard_metrics') or {}
            return {'priority_df': priority_df, 'metrics': metrics,
                    'uploaded_by': row.get('uploaded_by'), 'record_count': row.get('record_count', 0)}
    except Exception:
        pass
    return {'priority_df': pd.DataFrame(), 'metrics': {}, 'uploaded_by': None, 'record_count': 0}

@st.cache_data(ttl=30, show_spinner=False)
def pull_realtime(session_date: str) -> Optional[dict]:
    """ดึงผล Realtime"""
    try:
        client = get_supabase_client()
        result = client.table('cloud_realtime').select('*').eq('session_date', session_date).execute()
        if result.data:
            row = result.data[0]
            priority_df = pd.DataFrame(row.get('priority_json') or [])
            return {
                'priority_df':  priority_df,
                'upload_count': row.get('upload_count', 1),
                'first_time':   row.get('first_record_time'),
                'last_time':    row.get('last_record_time'),
                'record_count': row.get('record_count', 0),
                'uploaded_by':  row.get('uploaded_by'),
                'updated_at':   row.get('updated_at'),
            }
    except Exception:
        pass
    return None

@st.cache_data(ttl=300, show_spinner=False)
def pull_suspects(limit: int = 200) -> pd.DataFrame:
    """ดึงรถวิ่งซ้ำ"""
    try:
        client = get_supabase_client()
        result = client.table('cloud_suspects').select('*').order('seen_count', desc=True).limit(limit).execute()
        return pd.DataFrame(result.data or [])
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=60, show_spinner=False)
def pull_upload_log(limit: int = 50) -> pd.DataFrame:
    """ดึงประวัติการ Upload"""
    try:
        client = get_supabase_client()
        result = client.table('upload_log').select('*').order('uploaded_at', desc=True).limit(limit).execute()
        return pd.DataFrame(result.data or [])
    except Exception:
        return pd.DataFrame()

# ─── Sync Status ──────────────────────────────────────────────────────────────
def show_sync_status():
    """แสดง sync status ใน sidebar"""
    if not is_supabase_configured():
        st.sidebar.caption("⚠️ Supabase: ไม่ได้ตั้งค่า (Local Only)")
        return
    err = st.session_state.pop('_sync_error', None)
    if err:
        st.sidebar.error(f"☁️ Sync Error: {err[:80]}")
    else:
        st.sidebar.caption("☁️ Cloud Sync: พร้อม")
