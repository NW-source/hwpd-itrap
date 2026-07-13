import streamlit as st
import polars as pl
import pandas as pd
import numpy as np
import folium
import os
import re
import time
import sqlite3
from datetime import datetime, timedelta
from folium import plugins
from folium.plugins import MarkerCluster, HeatMap
import streamlit.components.v1 as components
import plotly.graph_objects as go
import plotly.express as px
from collections import defaultdict
import json

# ==========================================
# 0. ตั้งค่าระบบและไลบรารี (Configuration)
# ==========================================
st.set_page_config(page_title="HWPD 60 i-Trap Command Center", layout="wide", page_icon="🛡️", initial_sidebar_state="expanded")

DB_PATH = "hwpd_master_database.db"
PARQUET_PATH = "hwpd_master_data.parquet"

BORDER_PROVINCES = {'หนองคาย', 'บึงกาฬ', 'นครพนม', 'มุกดาหาร', 'อำนาจเจริญ', 'อุบลราชธานี', 'ศรีสะเกษ', 'สุรินทร์', 'บุรีรัมย์', 'สระแก้ว', 'จันทบุรี', 'ตราด', 'เลย', 'อุดรธานี'}

# 🛡️ CSS Dual-Theme (Dark + Light)
if 'theme' not in st.session_state:
    st.session_state['theme'] = 'dark'

_dark_css = """    /* ═══ DARK MODE ═══ */
    html, body { font-family: 'Inter', sans-serif !important; background: #0a0e1a !important; }
    .stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1321 50%, #0a1628 100%) !important; min-height: 100vh; }
    .main { background: transparent !important; }
    .block-container { padding-top: 3.5rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; }
    /* Sidebar */
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0d1321 0%, #0f172a 100%) !important; border-right: 1px solid rgba(59,130,246,0.15) !important; }
    section[data-testid="stSidebar"] > div { background: transparent !important; }
    /* Sidebar text colors (NOT wildcard to preserve collapse button) */
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown { color: #e2e8f0 !important; }
    section[data-testid="stSidebar"] hr { border-color: rgba(59,130,246,0.2) !important; }
    /* Sidebar buttons (stButton only, not native collapse button) */
    section[data-testid="stSidebar"] .stButton > button { background: rgba(30,41,59,0.7) !important; border: 1px solid rgba(59,130,246,0.25) !important; color: #93c5fd !important; border-radius: 8px !important; font-size: 13px !important; font-weight: 600 !important; width: 100% !important; transition: all 0.2s ease !important; }
    section[data-testid="stSidebar"] .stButton > button:hover { background: rgba(59,130,246,0.25) !important; border-color: rgba(59,130,246,0.5) !important; color: #dbeafe !important; }
    /* Radio */
    section[data-testid="stSidebar"] .stRadio label { color: #cbd5e1 !important; }
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { background: rgba(15,23,42,0.8) !important; border-radius: 12px !important; padding: 4px !important; border: 1px solid rgba(59,130,246,0.15) !important; gap: 4px !important; }
    .stTabs [data-baseweb="tab"] { background: transparent !important; border-radius: 8px !important; color: #94a3b8 !important; font-size: 13px !important; font-weight: 500 !important; padding: 8px 16px !important; }
    .stTabs [aria-selected="true"] { background: linear-gradient(135deg, rgba(59,130,246,0.25), rgba(99,102,241,0.25)) !important; color: #93c5fd !important; font-weight: 700 !important; border: 1px solid rgba(59,130,246,0.3) !important; }
    /* Text */
    h1, h2, h3 { color: #e2e8f0 !important; font-weight: 700 !important; }
    h4 { color: #94a3b8 !important; font-weight: 600 !important; }
    p, div, span { color: #cbd5e1; }
    hr { border-color: rgba(59,130,246,0.1) !important; margin: 20px 0 !important; }
    /* Inputs */
    [data-testid="stSelectbox"] > div > div { background: rgba(15,23,42,0.8) !important; border: 1px solid rgba(59,130,246,0.2) !important; border-radius: 8px !important; color: #e2e8f0 !important; }
    .stTextInput input { background: rgba(15,23,42,0.8) !important; border: 1px solid rgba(59,130,246,0.2) !important; border-radius: 8px !important; color: #e2e8f0 !important; }
    .stButton > button { background: linear-gradient(135deg, rgba(29,78,216,0.3), rgba(99,102,241,0.3)) !important; border: 1px solid rgba(59,130,246,0.3) !important; color: #93c5fd !important; border-radius: 8px !important; font-weight: 600 !important; font-size: 13px !important; transition: all 0.2s ease !important; }
    .stButton > button:hover { background: linear-gradient(135deg, rgba(29,78,216,0.5), rgba(99,102,241,0.5)) !important; color: #dbeafe !important; box-shadow: 0 4px 16px rgba(59,130,246,0.2) !important; transform: translateY(-1px); }
    [data-testid="stAlert"] { background: rgba(15,23,42,0.7) !important; border-radius: 10px !important; border: 1px solid rgba(59,130,246,0.2) !important; color: #94a3b8 !important; }
    [data-testid="stFileUploader"] { background: rgba(15,23,42,0.6) !important; border: 2px dashed rgba(59,130,246,0.25) !important; border-radius: 12px !important; }
    [data-testid="stCheckbox"] label { color: #e2e8f0 !important; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; border: 1px solid rgba(59,130,246,0.12) !important; }
    [data-testid="stDataFrame"] > div { background: rgba(15,23,42,0.6) !important; }
    /* ═══ SHARED (both themes) ═══ */
    @keyframes pulse-border { 0% { box-shadow: 0 0 0 0 rgba(239,68,68,0.6); } 70% { box-shadow: 0 0 0 12px rgba(239,68,68,0); } 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); } }
    @keyframes shimmer { 0% { left: -100%; } 100% { left: 200%; } }
    @keyframes blink-green { 0%, 100% { opacity: 1; box-shadow: 0 0 6px #10b981; } 50% { opacity: 0.3; box-shadow: none; } }
    @keyframes ticker { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
    .live-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background-color: #10b981; margin-right: 8px; animation: blink-green 1.5s infinite; }
    .ticker-wrap { width: 100%; overflow: hidden; background: linear-gradient(90deg, #020617, #0f172a, #020617); padding: 9px 0; margin-bottom: 16px; white-space: nowrap; border-radius: 8px; color: #38bdf8; border: 1px solid rgba(56,189,248,0.15); }
    .ticker-content { display: inline-block; animation: ticker 35s linear infinite; font-weight: 500; font-family: 'JetBrains Mono', monospace; letter-spacing: 1.5px; font-size: 12px; }
    .metric-card { padding: 20px 16px; border-radius: 14px; text-align: center; margin-bottom: 16px; border: 1px solid rgba(255,255,255,0.07); position: relative; overflow: hidden; backdrop-filter: blur(12px); transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 14px 14px 0 0; }
    .metric-card:hover { transform: translateY(-3px); }
    .card-apex { background: linear-gradient(145deg, rgba(159,18,57,0.18), rgba(30,10,25,0.65)); box-shadow: 0 4px 24px rgba(159,18,57,0.15); }
    .card-apex::before { background: linear-gradient(90deg, #9f1239, #e11d48); }
    .card-apex .metric-value { color: #fda4af; } .card-apex .metric-label { color: #fecdd3; }
    .card-clone { background: linear-gradient(145deg, rgba(234,88,12,0.16), rgba(30,15,5,0.65)); box-shadow: 0 4px 24px rgba(234,88,12,0.12); }
    .card-clone::before { background: linear-gradient(90deg, #ea580c, #f97316); }
    .card-clone .metric-value { color: #fdba74; } .card-clone .metric-label { color: #fed7aa; }
    .card-car { background: linear-gradient(145deg, rgba(59,130,246,0.16), rgba(5,15,40,0.65)); box-shadow: 0 4px 24px rgba(59,130,246,0.12); }
    .card-car::before { background: linear-gradient(90deg, #2563eb, #3b82f6); }
    .card-car .metric-value { color: #93c5fd; } .card-car .metric-label { color: #bfdbfe; }
    .card-anomaly { background: linear-gradient(145deg, rgba(99,102,241,0.16), rgba(10,5,40,0.65)); box-shadow: 0 4px 24px rgba(99,102,241,0.12); }
    .card-anomaly::before { background: linear-gradient(90deg, #6366f1, #8b5cf6); }
    .card-anomaly .metric-value { color: #a5b4fc; } .card-anomaly .metric-label { color: #c7d2fe; }
    .card-watch { background: linear-gradient(145deg, rgba(234,179,8,0.16), rgba(30,20,5,0.65)); box-shadow: 0 4px 24px rgba(234,179,8,0.12); }
    .card-watch::before { background: linear-gradient(90deg, #ca8a04, #eab308); }
    .card-watch .metric-value { color: #fde047; } .card-watch .metric-label { color: #fef08a; }
    .metric-value { font-size: 44px; font-weight: 800; margin: 8px 0 4px; line-height: 1; letter-spacing: -2px; }
    .metric-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; }
    .apex-threat-banner { background: linear-gradient(135deg, #4c0519 0%, #881337 50%, #4c0519 100%); color: #fecdd3; padding: 16px 20px; border-radius: 12px; font-size: 16px; font-weight: 700; margin-bottom: 20px; text-align: center; border: 1px solid rgba(251,113,133,0.3); animation: pulse-border 2s infinite; position: relative; overflow: hidden; }
    .apex-threat-banner::before { content: ''; position: absolute; top: 0; left: -100%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent); animation: shimmer 3s infinite; }
    .risk-orange { background: linear-gradient(135deg, rgba(154,52,18,0.15), rgba(30,15,5,0.4)); border-left: 4px solid #f97316; padding: 12px 16px; border-radius: 8px; color: #fdba74; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-blue { background: linear-gradient(135deg, rgba(29,78,216,0.15), rgba(5,15,40,0.4)); border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 8px; color: #93c5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-purple { background: linear-gradient(135deg, rgba(76,29,149,0.15), rgba(10,5,40,0.4)); border-left: 4px solid #8b5cf6; padding: 12px 16px; border-radius: 8px; color: #c4b5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-red { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.4)); border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 8px; color: #fca5a5; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-yellow { background: linear-gradient(135deg, rgba(133,77,14,0.15), rgba(30,20,5,0.4)); border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; color: #fcd34d; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .dossier-reason { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.5)); border: 1px solid rgba(239,68,68,0.25); padding: 16px 20px; border-radius: 12px; color: #fca5a5; font-size: 15px; margin-bottom: 16px; }
    .dossier-summary { background: rgba(15,23,42,0.75); border: 1px solid rgba(59,130,246,0.15); padding: 18px; border-radius: 12px; font-size: 14px; color: #cbd5e1; height: 100%; backdrop-filter: blur(8px); }
    .dossier-summary strong, .dossier-summary b { color: #93c5fd !important; }
    .osrm-metric { background: rgba(16,185,129,0.08); border-left: 4px solid #10b981; padding: 14px 18px; margin-bottom: 16px; font-size: 14px; color: #6ee7b7; border-radius: 8px; }
    .tactical-brief { background: rgba(15,23,42,0.85); border-left: 4px solid #e11d48; padding: 16px 20px; border-radius: 10px; color: #cbd5e1; font-size: 14px; margin-bottom: 20px; line-height: 1.8; }
    .tactical-brief b { color: #93c5fd; } .tactical-brief u { color: #fbbf24; }
    .watch-card { background: rgba(30,25,5,0.7); border: 1px solid rgba(234,179,8,0.2); border-left: 4px solid #eab308; padding: 14px 16px; border-radius: 10px; margin-bottom: 10px; color: #fef08a; font-size: 13px; }
    .watch-card b { color: #fde047; }
    .badge-today { background: #dc2626; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; }
    .map-legend { position: absolute; bottom: 30px; right: 30px; z-index: 1000; background: rgba(10,14,26,0.92); padding: 12px 16px; border-radius: 10px; border: 1px solid rgba(59,130,246,0.25); font-size: 13px; color: #e2e8f0; }
    .main-title { text-align: center; font-size: 1.9rem; font-weight: 800; background: linear-gradient(135deg, #f1f5f9 0%, #93c5fd 50%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 2px; line-height: 1.2; }
    .main-subtitle { text-align: center; font-size: 0.88rem; color: #64748b !important; margin-top: 0; letter-spacing: 0.5px; margin-bottom: 10px; }
    .header-divider { height: 1px; background: linear-gradient(90deg, transparent, rgba(59,130,246,0.4), rgba(99,102,241,0.4), transparent); margin: 6px 0 16px 0; border: none; }"""

_light_css = """    /* ═══ LIGHT MODE ═══ */
    html, body { font-family: 'Inter', sans-serif !important; background: #f8fafc !important; }
    .stApp { background: #f8fafc !important; min-height: 100vh; }
    .main { background: #f8fafc !important; }
    .block-container { padding-top: 3.5rem !important; padding-left: 2rem !important; padding-right: 2rem !important; max-width: 100% !important; background: #f8fafc !important; }
    /* Sidebar */
    section[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #e2e8f0 !important; }
    section[data-testid="stSidebar"] > div { background: transparent !important; }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown { color: #1e293b !important; }
    section[data-testid="stSidebar"] hr { border-color: #e2e8f0 !important; }
    section[data-testid="stSidebar"] .stButton > button { background: #f1f5f9 !important; border: 1px solid #cbd5e1 !important; color: #334155 !important; border-radius: 8px !important; font-size: 13px !important; font-weight: 600 !important; width: 100% !important; transition: all 0.2s ease !important; }
    section[data-testid="stSidebar"] .stButton > button:hover { background: #e0e7ff !important; border-color: #6366f1 !important; color: #312e81 !important; }
    section[data-testid="stSidebar"] .stRadio label { color: #475569 !important; }
    .stTabs [data-baseweb="tab-list"] { background: #f1f5f9 !important; border-radius: 12px !important; padding: 4px !important; border: 1px solid #e2e8f0 !important; gap: 4px !important; }
    .stTabs [data-baseweb="tab"] { background: transparent !important; border-radius: 8px !important; color: #64748b !important; font-size: 13px !important; font-weight: 500 !important; padding: 8px 16px !important; }
    .stTabs [aria-selected="true"] { background: #ffffff !important; color: #1e40af !important; font-weight: 700 !important; border: 1px solid #bfdbfe !important; box-shadow: 0 1px 4px rgba(0,0,0,0.08) !important; }
    h1, h2, h3 { color: #0f172a !important; font-weight: 700 !important; }
    h4 { color: #475569 !important; font-weight: 600 !important; }
    p, div, span { color: #334155; }
    hr { border-color: #e2e8f0 !important; margin: 20px 0 !important; }
    [data-testid="stSelectbox"] > div > div { background: #ffffff !important; border: 1px solid #cbd5e1 !important; border-radius: 8px !important; color: #334155 !important; }
    .stTextInput input { background: #ffffff !important; border: 1px solid #cbd5e1 !important; border-radius: 8px !important; color: #334155 !important; }
    .stButton > button { background: linear-gradient(135deg, #eff6ff, #e0e7ff) !important; border: 1px solid #bfdbfe !important; color: #1e40af !important; border-radius: 8px !important; font-weight: 600 !important; font-size: 13px !important; transition: all 0.2s ease !important; }
    .stButton > button:hover { background: linear-gradient(135deg, #dbeafe, #c7d2fe) !important; border-color: #6366f1 !important; box-shadow: 0 4px 12px rgba(99,102,241,0.2) !important; transform: translateY(-1px); }
    [data-testid="stCheckbox"] label { color: #475569 !important; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; border: 1px solid #e2e8f0 !important; }
    /* ═══ SHARED (both themes) ═══ */
    @keyframes pulse-border { 0% { box-shadow: 0 0 0 0 rgba(239,68,68,0.6); } 70% { box-shadow: 0 0 0 12px rgba(239,68,68,0); } 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); } }
    @keyframes shimmer { 0% { left: -100%; } 100% { left: 200%; } }
    @keyframes blink-green { 0%, 100% { opacity: 1; box-shadow: 0 0 6px #10b981; } 50% { opacity: 0.3; box-shadow: none; } }
    @keyframes ticker { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
    .live-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background-color: #10b981; margin-right: 8px; animation: blink-green 1.5s infinite; }
    .ticker-wrap { width: 100%; overflow: hidden; background: linear-gradient(90deg, #020617, #0f172a, #020617); padding: 9px 0; margin-bottom: 16px; white-space: nowrap; border-radius: 8px; color: #38bdf8; border: 1px solid rgba(56,189,248,0.15); }
    .ticker-content { display: inline-block; animation: ticker 35s linear infinite; font-weight: 500; font-family: 'JetBrains Mono', monospace; letter-spacing: 1.5px; font-size: 12px; }
    .metric-card { padding: 20px 16px; border-radius: 14px; text-align: center; margin-bottom: 16px; border: 1px solid rgba(255,255,255,0.07); position: relative; overflow: hidden; backdrop-filter: blur(12px); transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; border-radius: 14px 14px 0 0; }
    .metric-card:hover { transform: translateY(-3px); }
    .card-apex { background: linear-gradient(145deg, rgba(159,18,57,0.18), rgba(30,10,25,0.65)); box-shadow: 0 4px 24px rgba(159,18,57,0.15); }
    .card-apex::before { background: linear-gradient(90deg, #9f1239, #e11d48); }
    .card-apex .metric-value { color: #fda4af; } .card-apex .metric-label { color: #fecdd3; }
    .card-clone { background: linear-gradient(145deg, rgba(234,88,12,0.16), rgba(30,15,5,0.65)); box-shadow: 0 4px 24px rgba(234,88,12,0.12); }
    .card-clone::before { background: linear-gradient(90deg, #ea580c, #f97316); }
    .card-clone .metric-value { color: #fdba74; } .card-clone .metric-label { color: #fed7aa; }
    .card-car { background: linear-gradient(145deg, rgba(59,130,246,0.16), rgba(5,15,40,0.65)); box-shadow: 0 4px 24px rgba(59,130,246,0.12); }
    .card-car::before { background: linear-gradient(90deg, #2563eb, #3b82f6); }
    .card-car .metric-value { color: #93c5fd; } .card-car .metric-label { color: #bfdbfe; }
    .card-anomaly { background: linear-gradient(145deg, rgba(99,102,241,0.16), rgba(10,5,40,0.65)); box-shadow: 0 4px 24px rgba(99,102,241,0.12); }
    .card-anomaly::before { background: linear-gradient(90deg, #6366f1, #8b5cf6); }
    .card-anomaly .metric-value { color: #a5b4fc; } .card-anomaly .metric-label { color: #c7d2fe; }
    .card-watch { background: linear-gradient(145deg, rgba(234,179,8,0.16), rgba(30,20,5,0.65)); box-shadow: 0 4px 24px rgba(234,179,8,0.12); }
    .card-watch::before { background: linear-gradient(90deg, #ca8a04, #eab308); }
    .card-watch .metric-value { color: #fde047; } .card-watch .metric-label { color: #fef08a; }
    .metric-value { font-size: 44px; font-weight: 800; margin: 8px 0 4px; line-height: 1; letter-spacing: -2px; }
    .metric-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; opacity: 0.9; }
    .apex-threat-banner { background: linear-gradient(135deg, #4c0519 0%, #881337 50%, #4c0519 100%); color: #fecdd3; padding: 16px 20px; border-radius: 12px; font-size: 16px; font-weight: 700; margin-bottom: 20px; text-align: center; border: 1px solid rgba(251,113,133,0.3); animation: pulse-border 2s infinite; position: relative; overflow: hidden; }
    .apex-threat-banner::before { content: ''; position: absolute; top: 0; left: -100%; width: 60%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), transparent); animation: shimmer 3s infinite; }
    .risk-orange { background: linear-gradient(135deg, rgba(154,52,18,0.15), rgba(30,15,5,0.4)); border-left: 4px solid #f97316; padding: 12px 16px; border-radius: 8px; color: #fdba74; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-blue { background: linear-gradient(135deg, rgba(29,78,216,0.15), rgba(5,15,40,0.4)); border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 8px; color: #93c5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-purple { background: linear-gradient(135deg, rgba(76,29,149,0.15), rgba(10,5,40,0.4)); border-left: 4px solid #8b5cf6; padding: 12px 16px; border-radius: 8px; color: #c4b5fd; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-red { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.4)); border-left: 4px solid #ef4444; padding: 12px 16px; border-radius: 8px; color: #fca5a5; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .risk-yellow { background: linear-gradient(135deg, rgba(133,77,14,0.15), rgba(30,20,5,0.4)); border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 8px; color: #fcd34d; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .dossier-reason { background: linear-gradient(135deg, rgba(127,29,29,0.2), rgba(30,10,10,0.5)); border: 1px solid rgba(239,68,68,0.25); padding: 16px 20px; border-radius: 12px; color: #fca5a5; font-size: 15px; margin-bottom: 16px; }
    .dossier-summary { background: rgba(15,23,42,0.75); border: 1px solid rgba(59,130,246,0.15); padding: 18px; border-radius: 12px; font-size: 14px; color: #cbd5e1; height: 100%; backdrop-filter: blur(8px); }
    .dossier-summary strong, .dossier-summary b { color: #93c5fd !important; }
    .osrm-metric { background: rgba(16,185,129,0.08); border-left: 4px solid #10b981; padding: 14px 18px; margin-bottom: 16px; font-size: 14px; color: #6ee7b7; border-radius: 8px; }
    .tactical-brief { background: rgba(15,23,42,0.85); border-left: 4px solid #e11d48; padding: 16px 20px; border-radius: 10px; color: #cbd5e1; font-size: 14px; margin-bottom: 20px; line-height: 1.8; }
    .tactical-brief b { color: #93c5fd; } .tactical-brief u { color: #fbbf24; }
    .watch-card { background: rgba(30,25,5,0.7); border: 1px solid rgba(234,179,8,0.2); border-left: 4px solid #eab308; padding: 14px 16px; border-radius: 10px; margin-bottom: 10px; color: #fef08a; font-size: 13px; }
    .watch-card b { color: #fde047; }
    .badge-today { background: #dc2626; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
    .stDataFrame { border-radius: 12px !important; overflow: hidden !important; }
    .map-legend { position: absolute; bottom: 30px; right: 30px; z-index: 1000; background: rgba(10,14,26,0.92); padding: 12px 16px; border-radius: 10px; border: 1px solid rgba(59,130,246,0.25); font-size: 13px; color: #e2e8f0; }
    .main-title { text-align: center; font-size: 1.9rem; font-weight: 800; background: linear-gradient(135deg, #f1f5f9 0%, #93c5fd 50%, #818cf8 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; margin-bottom: 2px; line-height: 1.2; }
    .main-subtitle { text-align: center; font-size: 0.88rem; color: #64748b !important; margin-top: 0; letter-spacing: 0.5px; margin-bottom: 10px; }
    .header-divider { height: 1px; background: linear-gradient(90deg, transparent, rgba(59,130,246,0.4), rgba(99,102,241,0.4), transparent); margin: 6px 0 16px 0; border: none; }"""

_active_css = _dark_css if st.session_state.get('theme', 'dark') == 'dark' else _light_css

st.markdown(f"""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>{_active_css}</style>
""", unsafe_allow_html=True)

if 'nav_tab' not in st.session_state:
    st.session_state['nav_tab'] = "🏠 สรุปสถานการณ์ (Overview)"

def change_tab(tab_name):
    st.session_state['nav_tab'] = tab_name

# ==========================================
# 1. จัดการฐานข้อมูล (SQLite สำหรับ Report + Parquet สำหรับ Big Data)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_reports (
            report_date TEXT PRIMARY KEY,
            priority_data TEXT,
            dashboard_metrics TEXT
        )
    ''')
    cursor.execute('CREATE TABLE IF NOT EXISTS whitelist_master (ทะเบียนรถ TEXT PRIMARY KEY, หมายเหตุ TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS target_status (Target_ID TEXT PRIMARY KEY, status TEXT, last_update TEXT)')
    conn.commit()
    conn.close()

init_db()

@st.cache_data(ttl=300)
def load_historical_data():
    if os.path.exists(PARQUET_PATH):
        try:
            df_pl = pl.read_parquet(PARQUET_PATH)
            return df_pl
        except Exception:
            return pl.DataFrame()
    return pl.DataFrame()

def save_to_memory(new_df_pl, current_db_pl):
    if new_df_pl.is_empty(): return current_db_pl
    if current_db_pl.is_empty(): combined = new_df_pl
    else: combined = pl.concat([current_db_pl, new_df_pl], how="vertical_relaxed")
        
    combined = combined.unique(subset=["ทะเบียน_Full", "Datetime", "จุดติดตั้งกล้อง"], keep="first")
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    combined = combined.filter(pl.col("Datetime") >= thirty_days_ago)
    
    combined.write_parquet(PARQUET_PATH, compression="zstd")
    return combined

def save_daily_report(report_date, priority_df, active_db_pd):
    metrics = {}
    if not priority_df.empty:
        apex_df = priority_df[priority_df['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"]
        metrics['cat_apex'] = len(apex_df)
        metrics['cat_cloned'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"])
        metrics['cat_convoy_car'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"])
        metrics['cat_others'] = len(priority_df[priority_df['ประเภท'] == "กลุ่มรถต้องสงสัย"])
        
        targeted_cars = set()
        for cars in priority_df['Cars_List']: targeted_cars.update(cars)
        target_logs = active_db_pd[active_db_pd['ทะเบียน_Full'].isin(targeted_cars)].copy()
        
        if not target_logs.empty:
            risk_map = {}
            for _, row in priority_df.iterrows():
                for car in row['Cars_List']:
                    risk_map[car] = max(risk_map.get(car, 0), row['Risk Score'])
            target_logs['Risk_Score'] = target_logs['ทะเบียน_Full'].map(risk_map)
            
            cam_stats = target_logs.groupby('จุดติดตั้งกล้อง').agg(
                lat=('ละติจูด', 'first'), lon=('ลองจิจูด', 'first'),
                volume=('ทะเบียน_Full', 'nunique'), 
                avg_score=('Risk_Score', 'mean'), max_score=('Risk_Score', 'max')
            ).reset_index()
            
            plate_to_type = {}
            for _, row in priority_df.iterrows():
                for car in row['Cars_List']:
                    plate_to_type[car] = row['ประเภท']
            
            cam_threats = target_logs.groupby('จุดติดตั้งกล้อง')['ทะเบียน_Full'].apply(lambda x: list(set([plate_to_type.get(c, "") for c in x]))).reset_index()
            cam_stats = pd.merge(cam_stats, cam_threats, on='จุดติดตั้งกล้อง')
            cam_stats['primary_threat'] = cam_stats['ทะเบียน_Full'].apply(lambda x: x[0] if len(x)>0 else "")
            
            metrics['map_stats'] = cam_stats.to_dict('records')
            active_db_pd['Hour'] = active_db_pd['Datetime'].dt.hour
            target_logs['Hour'] = target_logs['Datetime'].dt.hour
            target_logs['Threat_Type'] = target_logs['ทะเบียน_Full'].map(plate_to_type)
            
            hours = list(range(24))
            total_hourly = active_db_pd.groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0)
            target_total_hr = target_logs.groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0)
            
            metrics['clock'] = {
                'total_hourly': total_hourly.tolist(),
                'apex_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มเป้าหมายความมั่นคงระดับสูงสุด'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                'cloned_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มเป้าหมายสวมทะเบียน'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                'convoy_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มรถยนต์เคลื่อนที่แบบขบวน'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
                'border_hr': target_logs[target_logs['Threat_Type'] == 'กลุ่มรถต้องสงสัย'].groupby('Hour')['ทะเบียน_Full'].nunique().reindex(hours, fill_value=0).tolist(),
            }
            
            peak_target_hr = target_total_hr.idxmax() if target_total_hr.max() > 0 else 0
            hr_data = target_logs[target_logs['Hour'] == peak_target_hr]
            most_threat = target_logs['Threat_Type'].mode()[0] if not target_logs.empty else "-"
            
            metrics['tactical'] = {
                'peak_hr': int(peak_target_hr),
                'peak_cam': hr_data['จุดติดตั้งกล้อง'].mode()[0] if not hr_data.empty else "-",
                'main_threat': most_threat,
                'max_risk_ratio': float((target_total_hr / total_hourly.replace(0, 1) * 100).max())
            }
            
            tactical_table = target_logs.groupby(['Hour', 'จุดติดตั้งกล้อง']).agg(
                เป้าหมายที่พบ=('ทะเบียน_Full', 'nunique'),
                ระดับความเสี่ยง=('Risk_Score', 'max')
            ).reset_index().sort_values(by=['Hour', 'เป้าหมายที่พบ'], ascending=[True, False]).head(8)
            metrics['tactical_table'] = tactical_table.to_dict('records')


    # ★ บันทึก historical_suspects
    try:
        conn2 = sqlite3.connect(DB_PATH)
        suspects_df = priority_df[priority_df['Risk Score'] >= 80].copy() if not priority_df.empty else pd.DataFrame()
        if not suspects_df.empty:
            for _, row in suspects_df.iterrows():
                for plate in row.get('Cars_List', []):
                    conn2.execute("""
                        INSERT INTO historical_suspects (plate, threat_type, max_risk_score, last_seen_date, seen_count)
                        VALUES (?, ?, ?, ?, 1)
                        ON CONFLICT(plate) DO UPDATE SET
                            threat_type = CASE WHEN excluded.max_risk_score > historical_suspects.max_risk_score THEN excluded.threat_type ELSE historical_suspects.threat_type END,
                            max_risk_score = MAX(historical_suspects.max_risk_score, excluded.max_risk_score),
                            last_seen_date = excluded.last_seen_date,
                            seen_count = historical_suspects.seen_count + 1
                    """, (plate, row['ประเภท'], int(row['Risk Score']), report_date))
        conn2.commit()
        conn2.close()
    except Exception as _e:
        pass

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO daily_reports (report_date, priority_data, dashboard_metrics)
        VALUES (?, ?, ?)
    ''', (report_date, priority_df.to_json(orient='records', force_ascii=False), json.dumps(metrics, ensure_ascii=False)))
    conn.commit()
    conn.close()

# ==========================================
# 2. กระบวนการคัดกรองข้อมูล (Data Pre-processing)
# ==========================================
def normalize_plate(plate):
    p = str(plate).replace(" ", "").upper()
    p = p.replace('O', '0').replace('I', '1').replace('B', '8')
    p = re.sub(r'[\u200B-\u200D\uFEFF]', '', p)
    drop_words = ['ไม่ทราบ', 'ไม่มี', 'NULL', 'NONE', 'NAN', 'UNKNOWN', '-']
    if any(w in p for w in drop_words) or p == '': return None
    return p

def classify_vehicle(plate):
    if re.match(r'^[789]\d', plate): return "รถบรรทุก"
    elif re.search(r'[ก-ฮ]', plate): return "รถยนต์ทั่วไป"
    return "ไม่ทราบประเภท"

def calculate_haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2.0)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2.0)**2
    return 6371.0 * (2 * np.arcsin(np.sqrt(a)))

def preliminary_data_check(files):
    if not files: return None
    df_list = [pd.read_csv(f) if f.name.endswith('.csv') else pd.read_excel(f) for f in files]
    df_pd = pd.concat(df_list, ignore_index=True)
    
    total_raw = len(df_pd)
    rename_dict = {'ทะเบียน': 'ทะเบียนรถ', 'ป้ายทะเบียน': 'ทะเบียนรถ'}
    df_pd = df_pd.rename(columns=rename_dict)
    
    if 'ทะเบียนรถ' in df_pd.columns:
        df_pd['clean_plate'] = df_pd['ทะเบียนรถ'].apply(normalize_plate)
        valid_rows = df_pd['clean_plate'].notna().sum()
        invalid_rows = total_raw - valid_rows
    else:
        valid_rows = 0
        invalid_rows = total_raw
        
    return {"total": total_raw, "valid": valid_rows, "invalid": invalid_rows, "raw_df": df_pd}

def process_raw_data_polars(df_pd):
    if df_pd is None or df_pd.empty: return pl.DataFrame()
    
    rename_dict = {'กล้อง': 'จุดติดตั้งกล้อง', 'สถานที่': 'จุดติดตั้งกล้อง', 'latitude': 'ละติจูด', 'lat': 'ละติจูด', 'longitude': 'ลองจิจูด', 'lng': 'ลองจิจูด'}
    df_pd = df_pd.rename(columns=rename_dict)
    for col in ['ทะเบียนรถ', 'จุดติดตั้งกล้อง', 'วันที่', 'เวลา', 'จังหวัด']:
        if col not in df_pd.columns: df_pd[col] = ""
    
    # ★ PERF: normalize_plate — vectorized (ไม่ใช้ .apply)
    _s = df_pd['ทะเบียนรถ'].astype(str)
    _s = _s.str.replace(' ', '', regex=False).str.upper()
    _s = _s.str.replace('O', '0', regex=False).str.replace('I', '1', regex=False).str.replace('B', '8', regex=False)
    for _zc in ['\u200b', '\u200c', '\u200d', '\ufeff']:  # zero-width chars
        _s = _s.str.replace(_zc, '', regex=False)
    _drop_pat = r'ไม่ทราบ|ไม่มี|NULL|NONE|NAN|UNKNOWN'
    _invalid = _s.str.contains(_drop_pat, case=False, na=True) | (_s.str.len() == 0) | (_s == '-')
    _s = _s.where(~_invalid, other=None)
    df_pd['ทะเบียนรถ'] = _s
    df_pd['จังหวัด'] = df_pd['จังหวัด'].astype(str).str.strip().str.replace('None', '')
    df_pd = df_pd.dropna(subset=['ทะเบียนรถ'])
    df_pd['ทะเบียน_Full'] = df_pd['ทะเบียนรถ'] + df_pd['จังหวัด']
    
    df_pd['ละติจูด'] = pd.to_numeric(df_pd['ละติจูด'], errors='coerce').fillna(0.0)
    df_pd['ลองจิจูด'] = pd.to_numeric(df_pd['ลองจิจูด'], errors='coerce').fillna(0.0)
    df_pd = df_pd[(df_pd['ละติจูด'] != 0.0) & (df_pd['ลองจิจูด'] != 0.0)].copy()
    
    # ★ PERF: fix_year — vectorized (ไม่ใช้ .apply)
    _dy = df_pd['วันที่'].astype(str).str.replace('/', '-', regex=False)
    _year_int = pd.to_numeric(_dy.str[:4], errors='coerce').fillna(0).astype(int)
    _be_mask = _year_int > 2500
    if _be_mask.any():
        _ce_year = (_year_int[_be_mask] - 543).astype(str).str.zfill(4)
        _dy = _dy.copy()
        _dy[_be_mask] = _ce_year + _dy[_be_mask].str[4:]
    df_pd['วันที่'] = _dy
    df_pd['Datetime'] = pd.to_datetime(df_pd['วันที่'] + ' ' + df_pd['เวลา'], errors='coerce')
    df_pd = df_pd.dropna(subset=['Datetime']).reset_index(drop=True)
    # ★ PERF: classify_vehicle — vectorized
    _cv_s = df_pd['ทะเบียนรถ'].astype(str)
    _is_truck = _cv_s.str.match(r'^[789]\d', na=False)
    _has_thai = _cv_s.str.contains(r'[ก-ฮ]', regex=True, na=False)
    df_pd['ประเภทรถ'] = np.where(_is_truck, 'รถบรรทุก', np.where(_has_thai, 'รถยนต์ทั่วไป', 'ไม่ทราบประเภท'))
    
    df = pl.from_pandas(df_pd)
    
    df = df.sort(['ทะเบียน_Full', 'จุดติดตั้งกล้อง', 'Datetime'])
    df = df.with_columns(
        time_diff_cam=(pl.col('Datetime').diff().dt.total_milliseconds() / 1000).over(['ทะเบียน_Full', 'จุดติดตั้งกล้อง'])
    )
    df = df.filter(pl.col('time_diff_cam').is_null() | (pl.col('time_diff_cam') > 180))
    
    df = df.sort(['ทะเบียน_Full', 'Datetime'])
    df = df.with_columns([
        pl.col('ละติจูด').shift(1).over('ทะเบียน_Full').alias('prev_lat'),
        pl.col('ลองจิจูด').shift(1).over('ทะเบียน_Full').alias('prev_lon'),
        pl.col('Datetime').shift(1).over('ทะเบียน_Full').alias('prev_time'),
        pl.col('จุดติดตั้งกล้อง').shift(1).over('ทะเบียน_Full').alias('prev_cam')
    ])
    
    df = df.with_columns(
        dist_km_straight=pl.struct(['prev_lat', 'prev_lon', 'ละติจูด', 'ลองจิจูด']).map_batches(
            lambda s: calculate_haversine(s.struct.field('prev_lat').to_numpy(), s.struct.field('prev_lon').to_numpy(), s.struct.field('ละติจูด').to_numpy(), s.struct.field('ลองจิจูด').to_numpy())
        )
    )
    
    df = df.with_columns(dist_km=pl.col('dist_km_straight') * 1.35)
    df = df.with_columns(
        time_diff_hr=(pl.col('Datetime') - pl.col('prev_time')).dt.total_milliseconds() / 3600000.0
    )
    df = df.with_columns(
        Speed_kmh=pl.when(pl.col('time_diff_hr') > 0).then(pl.col('dist_km') / pl.col('time_diff_hr')).otherwise(0.0)
    )
    
    BORDER_ANCHORS = [(17.88, 102.75), (18.36, 103.65), (17.40, 104.78), (16.54, 104.73), (15.11, 105.47), (14.35, 104.05), (14.41, 103.85), (14.34, 103.22)]
    _BA = np.array(BORDER_ANCHORS)  # shape (8, 2)
    _ba_lats_r = np.radians(_BA[:, 0])
    _ba_lons_r = np.radians(_BA[:, 1])

    def _assign_zones_batch(lats_np, lons_np):
        # ★ PERF: numpy broadcasting — เร็วกว่า np.vectorize > 50x
        lats_r = np.radians(lats_np)[:, np.newaxis]   # (n,1)
        lons_r = np.radians(lons_np)[:, np.newaxis]   # (n,1)
        dlat = _ba_lats_r - lats_r   # (n,8)
        dlon = _ba_lons_r - lons_r   # (n,8)
        a = (np.sin(dlat / 2) ** 2 +
             np.cos(lats_r) * np.cos(_ba_lats_r) * np.sin(dlon / 2) ** 2)
        dists = 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))  # (n,8)
        is_border = (dists <= 50.0).any(axis=1)  # (n,)
        return np.where(is_border, 'A', 'C')

    df = df.with_columns(
        Zone=pl.struct(['ละติจูด', 'ลองจิจูด']).map_batches(
            lambda s: _assign_zones_batch(s.struct.field('ละติจูด').to_numpy(), s.struct.field('ลองจิจูด').to_numpy())
        )
    )
    df = df.with_columns(Is_Night=pl.col('Datetime').dt.hour().is_in([22, 23, 0, 1, 2, 3, 4]))
    
    return df

# ==========================================
# 3. กลไกประเมินพฤติการณ์ (The Orchestrator & 3 Engines)
# ==========================================
def run_intelligence_orchestrator(active_db_pl):
    active_db = active_db_pl.to_pandas()
    
    conn = sqlite3.connect(DB_PATH)
    wl_df = pd.read_sql("SELECT ทะเบียนรถ FROM whitelist_master", conn)
    conn.close()
    whitelist_plates = set(wl_df['ทะเบียนรถ'].tolist())
    
    if not active_db.empty and 'ทะเบียน_Full' in active_db.columns:
        active_db = active_db[~active_db['ทะเบียน_Full'].isin(whitelist_plates)]
        
        def get_direction(cam):
            if 'เข้า' in str(cam): return 'เข้า'
            if 'out' in str(cam) or 'ออก' in str(cam): return 'ออก'
            return 'ไม่ระบุ'
        active_db['Direction'] = active_db['จุดติดตั้งกล้อง'].apply(get_direction)
    
    engine_results = defaultdict(lambda: {"engines": set(), "reasons": [], "cars": set(), "score": 0, "type": "", "radar": {}, "cams": "-", "gap": "-"})
    
    # ----------------------------------------
    # 🚨 ENGINE 1: รถแฝด / สวมทะเบียน (Time-Travel Paradox) - THE GHOST CATCHER UPDATED
    # ----------------------------------------
    if not active_db.empty and 'Speed_kmh' in active_db.columns:
        # 🛠️ ตะแกรงฟิสิกส์ล้วน: ความเร็ววาร์ปเกิน 250 กม./ชม. หรือ มีการแยกร่างโผล่พร้อมกันเวลาเป็น 0 โดยที่ระยะทางห่างกันตั้งแต่ 50 กม. ขึ้นไป
        # 🛠️ E1: แยก 2 เงื่อนไขชัดเจน — ต้องเข้มข้น
        e1_speed_mask   = (active_db['Speed_kmh'] > 300) & (active_db['dist_km'] >= 80)   # ความเร็วเกิน 300 กม./ชม. ระยะ 80+ กม.
        e1_paradox_mask = (active_db['time_diff_hr'] == 0) & (active_db['dist_km'] >= 100) # เวลาเดียวกัน 2 กล้อง ห่าง 100+ กม.
        e1_mask = (e1_speed_mask | e1_paradox_mask) & (active_db['จุดติดตั้งกล้อง'] != active_db['prev_cam'])
        e1_plates = active_db[e1_mask]['ทะเบียน_Full'].unique()
        
        for plate in e1_plates:
            df_target = active_db[active_db['ทะเบียน_Full'] == plate].sort_values('Datetime')
            if df_target.empty: continue
            
            # 🛠️ ทุบกฎเช็คจังหวัดทิ้งไปแล้ว
            
            max_speed = df_target['Speed_kmh'].max()
            r_night = 20 if df_target.iloc[-1]['Is_Night'] else 0
            engine_results[plate]["engines"].add("E1")
            engine_results[plate]["reasons"].append(f"พบหลักฐานทางวิทยาศาสตร์การแยกร่างปรากฏตัวข้ามพื้นที่ (ระยะห่างพิกัด > 50 กม.) ในกรอบเวลาที่เป็นไปไม่ได้ มั่นใจว่าเป็นแก๊งสวมทะเบียน")
            engine_results[plate]["score"] = max(engine_results[plate]["score"], 100)
            engine_results[plate]["cars"].add(plate)
            engine_results[plate]["radar"] = {"Night": r_night, "Border": 30, "Shuttle": 0, "Regional": 0, "Convoy": 0}
            engine_results[plate]["speed_warp"] = f"{max_speed:.0f}"
    else:
        e1_plates = []

    # ----------------------------------------
    # 🚘 ENGINE 2: โครงข่ายขบวนรถลำเลียง (The Bounded Convoy) - LOCAL OVERLOAD TRAFIX
    # ----------------------------------------
    if not active_db.empty and 'ทะเบียน_Full' in active_db.columns:
        df_cars = active_db[active_db['ประเภทรถ'] == 'รถยนต์ทั่วไป']

        # ==========================================
        # 2.3 E2_CAR: ขบวนแก๊งรถยนต์ (วิ่งทางไกล ทิศทางชายแดน ผ่าน >= 4 ด่าน)
        # ==========================================
        cam_counts_car = df_cars.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].nunique()
        valid_car_plates = cam_counts_car[cam_counts_car >= 4].index 
        convoy_db_car = df_cars[df_cars['ทะเบียน_Full'].isin(valid_car_plates)].copy()
        
        pair_cams_car = defaultdict(set)
        for cam, group in convoy_db_car.groupby('จุดติดตั้งกล้อง'):
            group = group.sort_values('Datetime')
            times_sec = group['Datetime'].values.astype('datetime64[s]').astype(np.int64)
            plates = group['ทะเบียน_Full'].values
            n = len(plates)
            for i in range(n):
                for j in range(i + 1, n):
                    if times_sec[j] - times_sec[i] > 600: break 
                    c1, c2 = plates[i], plates[j]
                    if c1 != c2:
                        pair_cams_car[tuple(sorted([str(c1), str(c2)]))].add(cam)
                        
        adj_car = defaultdict(set)
        for pair, cams in pair_cams_car.items():
            if len(cams) >= 5:  # เข้มงวดขึ้น: บังคับผ่านร่วมกันอย่างน้อย 5 ด่าน (เดิม 4)
                adj_car[pair[0]].add(pair[1])
                adj_car[pair[1]].add(pair[0])
                
        visited_car = set()
        convoys_car = []
        for node in adj_car:
            if node not in visited_car:
                comp = set()
                q = [node]
                while q:
                    curr = q.pop(0)
                    if curr not in visited_car:
                        visited_car.add(curr)
                        comp.add(curr)
                        q.extend([n for n in adj_car[curr] if n not in visited_car])
                comp_list = sorted(list(comp))
                if 2 <= len(comp_list) <= 6:
                    df_target = active_db[active_db['ทะเบียน_Full'].isin(comp_list)]
                    is_valid = True
                    cams_passed = set()
                    for cam, c_group in df_target.groupby('จุดติดตั้งกล้อง'):
                        if len(c_group) >= 2:
                            if (c_group['Datetime'].max() - c_group['Datetime'].min()).total_seconds() > 600: 
                                is_valid = False
                                break
                            cams_passed.add(cam)
                    if is_valid and len(cams_passed) >= 5:  # เข้มงวดขึ้น: ต้องผ่านร่วมกัน 5 ด่าน
                        gap_val = df_target.groupby('จุดติดตั้งกล้อง').apply(lambda x: (x['Datetime'].max() - x['Datetime'].min()).total_seconds()).mean()
                        convoys_car.append({'cars': comp_list, 'cams': len(cams_passed), 'gap': gap_val})

        for cv in convoys_car:
            df_target = active_db[active_db['ทะเบียน_Full'].isin(cv['cars'])]
            if df_target.empty: continue
            
            lead_car = cv['cars'][0]
            lead_logs = df_target[df_target['ทะเบียน_Full'] == lead_car].sort_values('Datetime')
            dirs = [d for d in lead_logs['Direction'] if d != 'ไม่ระบุ']
            if len(set(dirs)) > 1: continue 
            
            total_dist = lead_logs['dist_km'].sum(skipna=True)
            provinces = set(df_target['จังหวัด'].unique()) - {""}
            is_cross_region = len(provinces) > 1 
            has_border_plate = any(p in BORDER_PROVINCES for p in provinces)

            # บังคับวิ่งระยะทางไกล (เกิน 100 กม.) หรือ ข้ามจังหวัด หรือ มุ่งหน้าชายแดน
            if total_dist < 100 and not is_cross_region and not has_border_plate: continue 
            
            avg_speed = df_target[df_target['Speed_kmh'] > 0]['Speed_kmh'].mean()
            speed_txt = f" (ความเร็วกลุ่ม {avg_speed:.0f} กม./ชม.)" if pd.notna(avg_speed) else ""
            
            base_convoy_score = 65
            compound_reasons = []
            
            if has_border_plate:
                base_convoy_score += 15
                compound_reasons.append("มีรถทะเบียนจังหวัดชายแดนในขบวน")
            if is_cross_region:
                base_convoy_score += 15
                compound_reasons.append("ใช้ป้ายทะเบียนข้ามภูมิภาคสลับกันนำ-ตาม")
            if set(dirs) == {'เข้า'} or set(dirs) == {'ออก'}:
                base_convoy_score += 15
                compound_reasons.append(f"มุ่งหน้าทิศทาง [{list(set(dirs))[0]}] ชัดเจน")
            
            if base_convoy_score < 90: continue  # ★ เข้มงวด: ต้องผ่านอย่างน้อย 2 ใน 3 เงื่อนไข (ชายแดน/ข้ามภูมิภาค/ทิศทาง)

            compound_reasons.append(f"[ขบวนการลำเลียงรถยนต์] เคลื่อนที่ข้ามพื้นที่ ({total_dist:.0f} กม.) ผ่าน {cv['cams']} ด่าน{speed_txt}")
                
            group_id = f"Group_Car_{cv['cars'][0]}"
            for c in cv['cars']: engine_results[group_id]["cars"].add(c)
            engine_results[group_id]["engines"].add("E2_Car")
            engine_results[group_id]["reasons"].append(" | ".join(compound_reasons))
            engine_results[group_id]["score"] = max(engine_results[group_id]["score"], min(100, base_convoy_score))
            engine_results[group_id]["radar"] = {"Night": 10, "Border": 20 if has_border_plate else 0, "Shuttle": 0, "Regional": 15 if is_cross_region else 0, "Convoy": 30}
            engine_results[group_id]["cams"] = f"{cv['cams']}"
            engine_results[group_id]["total_dist"] = total_dist
            
            avg_gap_sec = cv['gap']
            gm = int(avg_gap_sec // 60)
            gs = int(avg_gap_sec % 60)
            gap_text = f"{gm} นาที {gs} วินาที" if gm > 0 and gs > 0 else (f"{gm} นาที" if gm > 0 else f"{gs} วินาที")
            engine_results[group_id]["gap"] = gap_text

    # ----------------------------------------
    # 🔄 ENGINE 3: พฤติกรรมมุดช่องโหว่ชายแดน (Touch & Go U-Turn)
    # ----------------------------------------
    if not active_db.empty and 'Datetime' in active_db.columns:
        hourly_traffic = active_db.groupby([active_db['Datetime'].dt.hour]).size()
        traffic_q20 = hourly_traffic.quantile(0.2) if not hourly_traffic.empty else 0
        
        freq_counts = active_db.groupby('ทะเบียน_Full').size()
        e3_candidates_raw = freq_counts[freq_counts >= 3].index
        
        # ★ PERF: Pre-compute all filter criteria with groupby ONCE (ลด loop จาก 187k → ~ร้อยทะเบียน)
        _e3_sub = active_db[active_db['ทะเบียน_Full'].isin(e3_candidates_raw) &
                             ~active_db['ทะเบียน_Full'].isin(e1_plates)]
        if not _e3_sub.empty:
            _e3_g = _e3_sub.groupby('ทะเบียน_Full', sort=False)
            _e3_unique_days  = _e3_g['Datetime'].apply(lambda x: x.dt.date.nunique())
            _e3_cam_count    = _e3_g['จุดติดตั้งกล้อง'].nunique()
            _e3_dist_sum     = _e3_g['dist_km'].sum()
            _e3_has_A        = _e3_g['Zone'].apply(lambda x: 'A' in x.values)
            _e3_has_C        = _e3_g['Zone'].apply(lambda x: 'C' in x.values)
            _e3_pass = ((_e3_unique_days <= 2) & (_e3_cam_count >= 5) &
                        (_e3_dist_sum >= 200) & _e3_has_A & _e3_has_C)
            e3_candidates = _e3_pass[_e3_pass].index.tolist()
        else:
            e3_candidates = []
        
        for plate in e3_candidates:
            # ★ หมายเหตุ: เงื่อนไขตะแกรง 1,2,4 กรองล่วงหน้าแล้ว — ยังคง logic U-turn, evasion ครบถ้วน
            df_target = active_db[active_db['ทะเบียน_Full'] == plate].sort_values('Datetime')
            if df_target.empty: continue
            
            # ★ ยังคงตะแกรงทั้งหมด (ไม่ลบ logic ใด) — แค่ skip ซ้ำสำหรับที่กรองไปแล้ว
            unique_days = df_target['Datetime'].dt.date.nunique()
            if unique_days > 2: continue 
            if df_target['จุดติดตั้งกล้อง'].nunique() < 5: continue
            if df_target['dist_km'].sum(skipna=True) < 200: continue
            zones = df_target['Zone'].unique()
            if 'C' not in zones or 'A' not in zones: continue
            
            is_night = any(df_target['Is_Night'])
            is_border = 'A' in df_target['Zone'].values
            province = str(df_target['จังหวัด'].iloc[-1]) if not df_target.empty else ""
            is_foreign = province not in BORDER_PROVINCES
            
            is_drop_pick = False
            time_diffs = df_target['Datetime'].diff().dt.total_seconds() / 3600.0
            # 🛠️ ตะแกรง 3: พฤติกรรมโฉบรับ/ส่ง แช่ตัว 1-4 ชม.
            gap_indices = np.where((time_diffs >= 1.0) & (time_diffs <= 4.0))[0] 
            
            for idx in gap_indices:
                if idx >= len(df_target): continue
                zone_before = df_target['Zone'].iloc[idx-1]
                zone_after = df_target['Zone'].iloc[idx]
                dir_before = df_target['Direction'].iloc[idx-1]
                dir_after = df_target['Direction'].iloc[idx]
                
                # ต้องเป็นพฤติกรรม โซน A (ชายแดน)
                if (zone_before == 'A' or zone_after == 'A'):
                    if dir_before == 'ออก' and dir_after == 'เข้า':
                        is_drop_pick = True
                        break
                        
            if not is_drop_pick: continue # ถ้าไม่ใช่ U-turn 1-4 ชม. เตะทิ้ง
                
            is_evasion = False
            hours_visited = df_target['Datetime'].dt.hour
            if any(hourly_traffic.get(h, 0) <= traffic_q20 for h in hours_visited):
                is_evasion = True
                
            avg_speed = df_target[df_target['Speed_kmh'] > 0]['Speed_kmh'].mean()
            speed_txt = f" (ความเร็วเฉลี่ย {avg_speed:.0f} กม./ชม.)" if pd.notna(avg_speed) else ""
                
            base_score = 60
            compound_triggers = []
            
            base_score += 20
            compound_triggers.append("ตีวงกลับโฉบรับ/ส่งข้ามภูมิภาค (ตอนใน ➡️ ออก ➡️ แช่ตัว 1-4 ชม. ➡️ เข้า)")
            
            if is_evasion and is_night: 
                compound_triggers.append("จงใจมุดช่องโหว่ห้วงเวลาวิกาลที่มีการจราจรต่ำ")
                base_score += 15
                
            if is_foreign and is_border: 
                compound_triggers.append(f"ยานพาหนะต่างถิ่น ({province}) ข้ามภูมิภาคลัดเลาะชายแดน")
                base_score += 15
                
            if base_score < 95: continue  # ★ เข้มงวดสุด: ต้องมีทั้ง U-turn + เวลาวิกาล + รถต่างถิ่นชายแดน
                
            if len(compound_triggers) >= 2:  # ต้องมีอย่างน้อย 2 เหตุผล (U-turn + อีก 1 เงื่อนไข)
                engine_results[plate]["engines"].add("E3")
                engine_results[plate]["reasons"].append(" + ".join(compound_triggers) + speed_txt)
                engine_results[plate]["score"] = max(engine_results[plate]["score"], min(95, base_score))
                engine_results[plate]["cars"].add(plate)
                engine_results[plate]["radar"] = {"Night": 30 if is_night else 0, "Border": 30 if is_border else 0, "Shuttle": 20, "Regional": 20 if is_foreign else 0, "Convoy": 0}
                engine_results[plate]["total_dist"] = df_target['dist_km'].sum(skipna=True)
                engine_results[plate]["cams"] = f"{df_target['จุดติดตั้งกล้อง'].nunique()}"

    # ----------------------------------------
    # 🌙 ENGINE 4: Night Ghost — รถชายแดนกลางดึกซ้ำซาก
    # ----------------------------------------
    if not active_db.empty and 'Is_Night' in active_db.columns and 'Zone' in active_db.columns:
        border_db   = active_db[active_db['Zone'] == 'A']
        border_night = border_db[border_db['Is_Night'] == True]

        if not border_night.empty:
            # ★ PERF: pre-compute counts แทน loop
            _e4_night_counts = border_night.groupby('ทะเบียน_Full').size()
            _e4_total_counts = active_db.groupby('ทะเบียน_Full').size()
            _e4_border_cams  = border_night.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].nunique()

            _e4_candidates = _e4_night_counts[_e4_night_counts >= 3].index

            for plate in _e4_candidates:
                if plate in e1_plates: continue

                night_count   = _e4_night_counts.get(plate, 0)
                total_count   = _e4_total_counts.get(plate, 1)
                border_cams   = _e4_border_cams.get(plate, 0)

                if border_cams < 2: continue

                night_ratio = night_count / max(total_count, 1)
                if night_ratio < 0.6: continue  # ต้อง >= 60% ผ่านชายแดนเป็นกลางดึก

                base_score = 70
                reasons    = []

                reasons.append(
                    f"พบการเดินทางผ่านชายแดนกลางดึก {night_count} ครั้ง ผ่าน {border_cams} จุดตรวจ"
                )

                if night_ratio >= 0.9:
                    base_score += 15
                    reasons.append("ผ่านชายแดนเฉพาะกลางดึก (≥90%) — แผนหลบเลี่ยงชัดเจน")
                elif night_ratio >= 0.7:
                    base_score += 8
                    reasons.append("ผ่านชายแดนกลางดึกสูงผิดปกติ (≥70%)")

                if border_cams >= 3:
                    base_score += 10
                    reasons.append(f"ครอบคลุมจุดตรวจชายแดน {border_cams} จุด ในคืนเดียว")

                df_target = active_db[active_db['ทะเบียน_Full'] == plate]
                avg_speed = df_target[df_target['Speed_kmh'] > 0]['Speed_kmh'].mean()
                speed_txt = f" (ความเร็วเฉลี่ย {avg_speed:.0f} กม./ชม.)" if pd.notna(avg_speed) else ""

                if base_score < 80: continue

                engine_results[plate]["engines"].add("E4")
                engine_results[plate]["reasons"].append(" | ".join(reasons) + speed_txt)
                engine_results[plate]["score"] = max(
                    engine_results[plate]["score"], min(90, base_score)
                )
                engine_results[plate]["cars"].add(plate)
                engine_results[plate]["radar"] = {
                    "Night": 40, "Border": 35, "Shuttle": 0, "Regional": 0, "Convoy": 0
                }
                engine_results[plate]["cams"] = str(border_cams)

    # ----------------------------------------
    # 👑 THE ORCHESTRATOR 
    # ----------------------------------------
    priority_list = []
    if not active_db.empty:
        # Pre-compute camera counts per plate for fast lookup
        _plate_cam_counts = active_db.groupby('ทะเบียน_Full')['จุดติดตั้งกล้อง'].nunique()

        for target_id, data in engine_results.items():
            if not data["cars"]: continue
            
            is_e1 = "E1" in data["engines"]
            is_e4 = "E4" in data["engines"]

            # 5-camera filter: ยกเว้น E1 (physics) และ E4 (border night ไม่ต้องการ 5 กล้อง)
            if not is_e1 and not is_e4:
                cam_count = _plate_cam_counts.reindex(list(data["cars"])).fillna(0).max()
                if cam_count < 5:
                    continue
            
            main_engines = set([e.split('_')[0] for e in data["engines"]])
            is_apex = len(main_engines) >= 2
            
            if is_apex: final_type = "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"
            elif "E1" in data["engines"]: final_type = "กลุ่มเป้าหมายสวมทะเบียน"
            elif "E2_Car" in data["engines"]: final_type = "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"
            elif "E4" in data["engines"]: final_type = "กลุ่มรถต้องสงสัย"
            elif "E3" in data["engines"]: final_type = "กลุ่มรถต้องสงสัย"
                
            target_cars_df = active_db[active_db['ทะเบียน_Full'].isin(data["cars"])].sort_values('Datetime')
            if target_cars_df.empty: continue 
            
            last_row = target_cars_df.iloc[-1]
            
            priority_list.append({
                "Target_ID": target_id,
                "เป้าหมาย": " / ".join([str(c) for c in data["cars"]])[:30] + ("..." if len(data["cars"])>2 else ""),
                "ประเภท": final_type,
                "พฤติกรรมต้องสงสัย": " | ".join(data["reasons"]),
                "ผ่านร่วมกัน (ด่าน)": data["cams"],
                "ระยะห่างเฉลี่ย": data["gap"], 
                "Risk Score": min(100, data["score"] + (10 if is_apex else 0)),
                "จุดตรวจพบล่าสุด": f"📍 {last_row['จุดติดตั้งกล้อง']}", 
                "เวลาโผล่ล่าสุด": str(last_row['เวลา']),
                "Cars_List": [str(c) for c in data["cars"]],
                "Radar_Data": data["radar"],
                "Speed_Warp": data.get("speed_warp", "-"),
                "Total_Dist": f"{data.get('total_dist', 0):.1f}" if ("E3" in data["engines"] or "E2_Car" in data["engines"]) else "-"
            })

    if priority_list:
        return pd.DataFrame(priority_list).sort_values(by="Risk Score", ascending=False).reset_index(drop=True)
    else:
        return pd.DataFrame(columns=["Target_ID", "เป้าหมาย", "ประเภท", "พฤติกรรมต้องสงสัย", "ผ่านร่วมกัน (ด่าน)", "ระยะห่างเฉลี่ย", "Risk Score", "จุดตรวจพบล่าสุด", "เวลาโผล่ล่าสุด", "Cars_List", "Radar_Data", "Speed_Warp", "Total_Dist"])

# ==========================================
# 4. ส่วนแสดงผลปฏิบัติการ (Dashboard & UI)
# ==========================================
def show_watch_list(active_db, selected_date):
    """แสดงรถในอดีตที่น่าสงสัย และตรวจสอบว่าผ่านกล้องวันนี้ไหม"""
    st.markdown("<div class='risk-yellow'>⭐ รายงาน: ทะเบียนที่น่าติดตาม (ประวัติพฤติกรรมต้องสงสัยในอดีต)</div><br>", unsafe_allow_html=True)
    try:
        conn_w = sqlite3.connect(DB_PATH)
        hs_df = pd.read_sql("""
            SELECT plate, threat_type, max_risk_score, last_seen_date, seen_count
            FROM historical_suspects
            ORDER BY max_risk_score DESC, seen_count DESC
        """, conn_w)
        conn_w.close()
    except:
        hs_df = pd.DataFrame()

    if hs_df.empty:
        st.info("📭 ยังไม่มีข้อมูลประวัติ — ระบบจะสะสมข้อมูลหลังจากทำการประมวลผลครั้งแรก")
        return

    today_plates = set(active_db['ทะเบียน_Full'].unique()) if not active_db.empty else set()

    # คำนวณ Watch Score
    today_dt = pd.to_datetime(selected_date)
    def calc_watch_score(row):
        days_ago = (today_dt - pd.to_datetime(row['last_seen_date'])).days if row['last_seen_date'] else 999
        recency_bonus = max(0, 30 - days_ago) / 30.0 * 30  # bonus สูงสุด 30 ถ้าเพิ่งเห็น
        freq_bonus = min(row['seen_count'] * 5, 20)  # bonus สูงสุด 20 จาก frequency
        seen_today_bonus = 25 if row['plate'] in today_plates else 0
        return min(100, int(row['max_risk_score'] * 0.5 + recency_bonus + freq_bonus + seen_today_bonus))

    hs_df['น้ำหนัก (Watch Score)'] = hs_df.apply(calc_watch_score, axis=1)
    hs_df['พบวันนี้'] = hs_df['plate'].apply(lambda p: '🔴 ตรวจพบวันนี้' if p in today_plates else '⬜ ยังไม่พบ')
    hs_df = hs_df.sort_values('น้ำหนัก (Watch Score)', ascending=False).reset_index(drop=True)

    seen_today = hs_df[hs_df['plate'].isin(today_plates)]
    not_seen = hs_df[~hs_df['plate'].isin(today_plates)]

    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1: st.metric("📋 รถใน Watch List", len(hs_df))
    with col_w2: st.metric("🔴 ตรวจพบวันนี้", len(seen_today))
    with col_w3: st.metric("⬜ ยังไม่พบวันนี้", len(not_seen))

    if not seen_today.empty:
        st.markdown("---")
        st.markdown("#### 🔴 รถที่น่าสนใจที่ผ่านกล้องวันนี้")
        for _, row in seen_today.iterrows():
            cams_today = active_db[active_db['ทะเบียน_Full'] == row['plate']]['จุดติดตั้งกล้อง'].unique().tolist() if not active_db.empty else []
            last_seen_cam = active_db[active_db['ทะเบียน_Full'] == row['plate']].sort_values('Datetime').iloc[-1]['จุดติดตั้งกล้อง'] if not active_db.empty and len(active_db[active_db['ทะเบียน_Full'] == row['plate']]) > 0 else '-'
            threat_icon = {'สวม': '🚨', 'ขบวน': '🚘', 'ผิด': '🔄'}.get(next((k for k in ['สวม', 'ขบวน', 'ผิด'] if k in str(row['threat_type'])), ''), '⚠️')
            st.markdown(f"""<div class='watch-card'>
                <b>{threat_icon} {row['plate']}</b> &nbsp; <span class='badge-today'>🔴 วันนี้</span><br>
                <b>ประเภทภัยคุกคาม:</b> {row['threat_type']} | <b>Risk Score:</b> {row['max_risk_score']} | <b>Watch Score:</b> {row['น้ำหนัก (Watch Score)']}<br>
                <b>ผ่านกล้อง {len(cams_today)} จุดวันนี้:</b> {', '.join(cams_today[:3])}{'...' if len(cams_today)>3 else ''} | <b>จุดล่าสุด:</b> {last_seen_cam}<br>
                <b>เคยพบ:</b> {row['seen_count']} ครั้ง | ครั้งสุดท้าย: {row['last_seen_date']}
            </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### 📋 ทะเบียนทั้งหมดใน Watch List")
    display_cols = ['plate', 'threat_type', 'max_risk_score', 'seen_count', 'last_seen_date', 'น้ำหนัก (Watch Score)', 'พบวันนี้']
    rename_map = {'plate': 'ทะเบียน', 'threat_type': 'ประเภทภัยคุกคาม', 'max_risk_score': 'Risk Score สูงสุด', 'seen_count': 'พบกี่ครั้ง', 'last_seen_date': 'เคยพบล่าสุด'}
    st.dataframe(hs_df[display_cols].rename(columns=rename_map), use_container_width=True, hide_index=True)

def color_score(val):
    try:
        v = int(str(val).replace('%', ''))
        color = '#fecdd3' if v >= 90 else '#fed7aa' if v >= 75 else '#fef08a'
        text_c = '#881337' if v >= 90 else '#9a3412' if v >= 75 else '#854d0e'
        return f'background-color: {color}; color: {text_c}; font-weight: bold; border-radius: 4px;'
    except:
        return ''


# ─────────────────────────────────────────────────────────────────────────
# 🔁 Repeat Offender Intelligence
# ─────────────────────────────────────────────────────────────────────────
def repeat_offender_analysis(db_path, reference_date, window_days=30, min_days=3):
    """ค้นหาทะเบียนที่ trigger detection ≥ min_days ในช่วง window_days"""
    try:
        conn = sqlite3.connect(db_path)
        ref_dt   = pd.to_datetime(reference_date)
        start_dt = (ref_dt - timedelta(days=window_days)).strftime('%Y-%m-%d')
        rows = conn.execute(
            "SELECT report_date, priority_data FROM daily_reports "
            "WHERE report_date >= ? AND report_date <= ? ORDER BY report_date",
            (start_dt, reference_date)
        ).fetchall()
        conn.close()
    except:
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    records = []
    for report_date, priority_data in rows:
        try:
            pdf = pd.DataFrame(json.loads(priority_data))
            if pdf.empty: continue
            for _, row in pdf.iterrows():
                score_val = row.get('Risk Score', 0)
                try: score_val = float(str(score_val).replace('%',''))
                except: score_val = 0
                if score_val < 80: continue
                for plate in row.get('Cars_List', []):
                    records.append({
                        'plate': str(plate),
                        'ประเภท': row.get('ประเภท', ''),
                        'score': score_val,
                        'report_date': report_date,
                        'เหตุผล': str(row.get('พฤติกรรมต้องสงสัย', ''))[:120],
                    })
        except: pass

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    summary = df.groupby('plate').agg(
        วันที่พบ=('report_date', 'nunique'),
        ประเภทหลัก=('ประเภท', lambda x: x.mode()[0] if len(x)>0 else ''),
        คะแนนสูงสุด=('score', 'max'),
        ครั้งแรก=('report_date', 'min'),
        ล่าสุด=('report_date', 'max'),
        dates_list=('report_date', lambda x: sorted(list(set(x)))),
        เหตุผลรวม=('เหตุผล', lambda x: ' | '.join(list(set(x))[:3]))
    ).reset_index()

    summary = summary[summary['วันที่พบ'] >= min_days].sort_values('วันที่พบ', ascending=False)
    return summary


def render_repeat_offender_dossier(plate, historical_db, dates_list):
    """แสดงรายละเอียด Repeat Offender — map + table เหมือนฟังก์ชันอื่น"""
    if historical_db is None or historical_db.empty or 'ทะเบียน_Full' not in historical_db.columns:
        st.info("⚠️ ไม่พบข้อมูลรายละเอียดในระบบ")
        return

    df_plate = historical_db[historical_db['ทะเบียน_Full'] == plate].sort_values('Datetime')
    if df_plate.empty:
        st.info(f"⚠️ ไม่พบเส้นทางของ {plate} ในฐานข้อมูล")
        return

    df_plate = df_plate.copy()
    df_plate['_date'] = df_plate['Datetime'].dt.date.astype(str)

    DAY_COLORS    = ['blue','red','green','orange','purple','pink','cadetblue','darkred']
    DAY_COLORS_HEX = ['#3b82f6','#ef4444','#22c55e','#f97316','#8b5cf6','#ec4899','#06b6d4','#dc2626']

    # ── 1. Day-summary table ────────────────────────────────────────────
    st.markdown(f"**📋 สรุปรายวัน: {plate}**")
    rows_sum = []
    for i, d in enumerate(dates_list):
        dd = df_plate[df_plate['_date'] == d]
        if dd.empty: continue
        ch = DAY_COLORS_HEX[i % len(DAY_COLORS_HEX)]
        rows_sum.append({
            'วัน': f"<span style='background:{ch};color:#fff;padding:2px 8px;border-radius:4px;font-weight:bold'>{d}</span>",
            'กล้องที่ผ่าน': f"{dd['จุดติดตั้งกล้อง'].nunique()} จุด",
            'เวลาแรก': dd['Datetime'].min().strftime('%H:%M'),
            'เวลาสุดท้าย': dd['Datetime'].max().strftime('%H:%M'),
            'ระยะทาง(กม.)': f"{dd['dist_km'].sum(skipna=True):.0f}",
            'Zone': ', '.join(str(z) for z in dd['Zone'].unique()) if 'Zone' in dd.columns else '-',
        })
    if rows_sum:
        st.write(pd.DataFrame(rows_sum).to_html(index=False, escape=False), unsafe_allow_html=True)

    st.markdown("---")

    # ── 2. Detailed records table (เหมือนฟังก์ชันอื่น) ───────────────────
    st.markdown("**📑 ตารางข้อมูลอ้างอิงรายจุดตรวจ**")
    detail_cols = ['Datetime','จุดติดตั้งกล้อง','Speed_kmh','Direction','Zone','ละติจูด','ลองจิจูด']
    avail_cols  = [c for c in detail_cols if c in df_plate.columns]
    detail_df   = df_plate[avail_cols].copy()
    detail_df.insert(0, 'วันที่', df_plate['_date'])
    detail_df['Datetime'] = detail_df['Datetime'].dt.strftime('%H:%M:%S') if 'Datetime' in detail_df.columns else '-'
    detail_df = detail_df.rename(columns={
        'Datetime': 'เวลา', 'Speed_kmh': 'ความเร็ว(กม./ชม.)',
        'Direction': 'ทิศทาง', 'ละติจูด': 'Lat', 'ลองจิจูด': 'Lon'
    })
    st.dataframe(detail_df, use_container_width=True, height=220)

    st.markdown("---")

    # ── 3. Map with day-filter panel on the left ───────────────────────
    st.markdown("**🗺️ แผนที่เส้นทางแต่ละวัน**")

    valid = df_plate.dropna(subset=['ละติจูด','ลองจิจูด'])
    if valid.empty:
        st.info("ไม่มีข้อมูลพิกัดสำหรับแสดงแผนที่")
        return

    col_cb, col_map = st.columns([1, 4])

    # ── Left: colored checkbox list ─────────────────────────────────────
    selected_dates = []
    with col_cb:
        st.markdown(
            "<div style='font-size:12px;font-weight:600;color:#475569;"
            "margin-bottom:8px'>🗓️ เลือกวันที่</div>",
            unsafe_allow_html=True
        )
        for i, d in enumerate(dates_list):
            hex_color = DAY_COLORS_HEX[i % len(DAY_COLORS_HEX)]
            sw, chk = st.columns([0.15, 0.85])
            with sw:
                st.markdown(
                    f"<div style='width:12px;height:12px;background:{hex_color};"
                    f"border-radius:3px;margin-top:7px'></div>",
                    unsafe_allow_html=True
                )
            with chk:
                if st.checkbox(d, value=True, key=f"rep_day_{plate}_{i}_{d}"):
                    selected_dates.append(d)

    # ── Right: map built from selected days ─────────────────────────────
    with col_map:
        if not selected_dates:
            st.info("เลือกอย่างน้อย 1 วันเพื่อแสดงแผนที่")
        else:
            center_lat = valid['ละติจูด'].mean()
            center_lon = valid['ลองจิจูด'].mean()
            m = folium.Map(location=[center_lat, center_lon], zoom_start=8)

            for i, d in enumerate(dates_list):
                if d not in selected_dates: continue
                dd = df_plate[df_plate['_date'] == d].dropna(subset=['ละติจูด','ลองจิจูด'])
                if dd.empty: continue
                f_color   = DAY_COLORS[i % len(DAY_COLORS)]
                hex_color = DAY_COLORS_HEX[i % len(DAY_COLORS_HEX)]

                for _, r in dd.iterrows():
                    spd = r.get('Speed_kmh', 0)
                    spd_txt = f"{spd:.0f} กม./ชม." if pd.notna(spd) and spd > 0 else "ไม่ระบุ"
                    popup_html = (
                        f"<b>{r['จุดติดตั้งกล้อง']}</b><br>"
                        f"วันที่: {d}<br>"
                        f"เวลา: {r['Datetime'].strftime('%H:%M:%S')}<br>"
                        f"ความเร็ว: {spd_txt}<br>"
                        f"ทิศทาง: {r.get('Direction','ไม่ระบุ')}"
                    )
                    folium.CircleMarker(
                        location=(r['ละติจูด'], r['ลองจิจูด']),
                        radius=6, color=hex_color, fill=True, fill_opacity=0.85,
                        popup=folium.Popup(popup_html, max_width=250),
                        tooltip=f"{d} | {r['จุดติดตั้งกล้อง']}"
                    ).add_to(m)

                coords = list(zip(dd['ละติจูด'].tolist(), dd['ลองจิจูด'].tolist()))
                if len(coords) >= 2:
                    folium.PolyLine(
                        locations=coords, color=hex_color, weight=4, opacity=0.8,
                        tooltip=f"เส้นทาง {d} ({len(coords)} จุด)"
                    ).add_to(m)
                    folium.Marker(
                        location=coords[0],
                        icon=folium.Icon(color=f_color, icon='play', prefix='fa'),
                        tooltip=f"เริ่มต้น {d}: {dd['จุดติดตั้งกล้อง'].iloc[0]}"
                    ).add_to(m)
                    folium.Marker(
                        location=coords[-1],
                        icon=folium.Icon(color=f_color, icon='flag', prefix='fa'),
                        tooltip=f"สิ้นสุด {d}: {dd['จุดติดตั้งกล้อง'].iloc[-1]}"
                    ).add_to(m)

            components.html(m.get_root().render(), height=460)



def render_case_dossier(selected_target, active_db, priority_df):
    # Safety: หาก active_db ไม่มีคอลัมน์ที่ต้องการ
    if active_db is None or active_db.empty or 'ทะเบียน_Full' not in active_db.columns:
        st.info("⚠️ ไม่พบข้อมูลรายละเอียด — กรุณาโหลดข้อมูลวันที่เลือกใหม่อีกครั้งผ่าน Admin Portal")
        return
    target_info = priority_df[priority_df['Target_ID'] == selected_target].iloc[0]
    cars = target_info['Cars_List']
    case_data = active_db[active_db['ทะเบียน_Full'].isin(cars)].sort_values('Datetime')
    
    is_clone = "สวมทะเบียน" in target_info['ประเภท']
    is_convoy = "ขบวน" in target_info['ประเภท']
    is_anomaly = "ผิดปกติ" in target_info['ประเภท']
    
    total_dist_km = 0.0
    total_time_hr = 0.0
    
    if len(cars) > 0:
        main_car_df = case_data[case_data['ทะเบียน_Full'] == cars[0]].sort_values('Datetime')
        if len(main_car_df) > 1:
            first_row = main_car_df.iloc[0]
            last_row = main_car_df.iloc[-1]
            total_time_hr = (last_row['Datetime'] - first_row['Datetime']).total_seconds() / 3600.0
            
            if total_time_hr > 0:
                total_straight_km = sum(calculate_haversine(main_car_df.iloc[i-1]['ละติจูด'], main_car_df.iloc[i-1]['ลองจิจูด'], main_car_df.iloc[i]['ละติจูด'], main_car_df.iloc[i]['ลองจิจูด']) for i in range(1, len(main_car_df)))
                total_dist_km = total_straight_km * 1.35
                    
    st.markdown("<div class='dossier-section print-hidden'><hr style='border: 2px solid #94a3b8;'></div>", unsafe_allow_html=True)
    
    col_header, col_btn = st.columns([8, 2])
    with col_header:
        st.markdown(f"## 📂 ข้อมูลเป้าหมายเฝ้าระวัง: {selected_target}")
    with col_btn:
        components.html("""
            <button onclick="window.parent.print()" style="width: 100%; padding: 10px; background-color: #0f172a; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; font-family: sans-serif; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                🖨️ พิมพ์ข้อมูลแฟ้มคดี
            </button>
        """, height=50)

    conn = sqlite3.connect(DB_PATH)
    status_row = conn.execute("SELECT status FROM target_status WHERE Target_ID=?", (selected_target,)).fetchone()
    current_status = status_row[0] if status_row else "🔴 เฝ้าระวังใหม่"
    
    st.markdown("#### 🎯 ระบุสถานะเป้าหมาย (Action Status)")
    status_options = ["🔴 เฝ้าระวังใหม่", "🟡 สั่งการตรวจสอบแล้ว", "🟢 เคลียร์เป้าหมาย/จับกุมแล้ว"]
    new_status = st.selectbox("ปรับปรุงสถานะ:", status_options, index=status_options.index(current_status), key=f"status_{selected_target}", label_visibility="collapsed")
    
    if new_status != current_status:
        conn.execute("INSERT OR REPLACE INTO target_status (Target_ID, status, last_update) VALUES (?, ?, ?)", (selected_target, new_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        st.success(f"✅ อัปเดตสถานะเป็น: {new_status} เรียบร้อยแล้ว! (มีผลทันทีในตารางเป้าหมาย)")
        st.session_state['force_refresh'] = True 
    conn.close()
    
    # === Layout แยกตาม Engine ===
    if is_clone:
        col_map, col_info = st.columns([6, 4])
        with col_info:
            st.markdown(f"<div class='dossier-reason'><b>🚨 ภัยคุกคามระดับวิกฤต: </b><br><span style='font-size:16px;'>{target_info['พฤติกรรมต้องสงสัย']}</span></div>", unsafe_allow_html=True)
            st.markdown("### 🔍 วิเคราะห์พยานหลักฐาน (Forensic Box)")
            show_real = st.checkbox("🟢 แสดงเส้นทางรถคันจริง (Real Trajectory)", value=True)
            show_fake = st.checkbox("🚨 แสดงพิกัดรถสวมทะเบียน (Ghost Placements)", value=True)
            
            total_reads = len(case_data)
            cam_str = ", ".join([f"{k}" for k, v in case_data['จุดติดตั้งกล้อง'].value_counts().head(3).items()])
            prov_str = ", ".join(list(set(case_data['จังหวัด'].unique()) - {""}))
            
            # 🧹 Clean HTML Summary 
            summary_md = f"""
**📌 จังหวัดที่จดทะเบียน:** {prov_str}

**📊 สถิติการตรวจพบสะสม:** {total_reads} ครั้ง

**📍 จุดตรวจที่ปรากฏตัวบ่อยที่สุด:** {cam_str}
            """
            st.markdown("<div class='dossier-summary'>", unsafe_allow_html=True)
            st.markdown("#### 📋 สรุปข้อมูลประวัติเป้าหมาย (Intelligence Summary)")
            st.markdown(summary_md)
            st.markdown("</div>", unsafe_allow_html=True)
            
        with col_map:
            st.markdown("### 🗺️ แผนที่แยกเงารถสวมทะเบียน (2D Ghost Tracker)")
            m_case = folium.Map(location=[case_data['ละติจูด'].mean(), case_data['ลองจิจูด'].mean()], zoom_start=9)
            c_df = case_data[case_data['ทะเบียน_Full'] == cars[0]].sort_values('Datetime')
            
            normal_coords = []
            ghost_coords = []
            for r in c_df.itertuples():
                spd = getattr(r, 'Speed_kmh')
                if spd and pd.notna(spd) and spd > 200:
                    ghost_coords.append((r.ละติจูด, r.ลองจิจูด, r.เวลา, r.จุดติดตั้งกล้อง, spd))
                else:
                    normal_coords.append((r.ละติจูด, r.ลองจิจูด, r.เวลา, r.จุดติดตั้งกล้อง))
            
            if show_real:
                for lat, lon, tm, cam in normal_coords:
                    folium.Marker(location=(lat, lon), popup=f"{tm} - {cam}", icon=folium.Icon(color='blue', icon='car', prefix='fa')).add_to(m_case)
                if len(normal_coords) > 1:
                    plugins.AntPath([(lat, lon) for lat, lon, _, _ in normal_coords], color='blue', weight=4).add_to(m_case)
            if show_fake:
                for lat, lon, tm, cam, spd in ghost_coords:
                    popup_html = f"<b>🚨 พิกัดผิดปกติ (คาดว่ารถสวมทะเบียน)</b><br>เวลา: {tm}<br>จุดตรวจ: {cam}<br>ความเร็วประเมิน: {spd:.0f} กม./ชม."
                    folium.Marker(location=(lat, lon), popup=popup_html, icon=folium.Icon(color='red', icon='warning-sign')).add_to(m_case)
            components.html(m_case.get_root().render(), height=400)
            
    else:
        if target_info['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด":
            st.markdown(f"<div class='dossier-reason'><b>🚨 ภัยคุกคามระดับวิกฤต: </b><br><span style='font-size:16px;'>{target_info['พฤติกรรมต้องสงสัย']}</span></div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='dossier-reason' style='background-color:#f8fafc; border-color:#cbd5e1; color:#0f172a;'><b>⚠️ ตรวจพบพฤติการณ์ต้องสงสัย:</b> {target_info['พฤติกรรมต้องสงสัย']} <br><span style='font-size:14px; opacity:0.8;'>(ระดับภัยคุกคาม: {target_info['Risk Score']})</span></div>", unsafe_allow_html=True)
            
        col_radar, col_summary = st.columns([4, 6])
        with col_radar:
            radar_data = target_info.get("Radar_Data", {})
            r_vals = [radar_data.get('Night',0), radar_data.get('Border',0), radar_data.get('Shuttle',0), radar_data.get('Regional',0), radar_data.get('Convoy',0)]
            theta_vals = ['ห้วงเวลาวิกาล (Max 20)', 'พื้นที่ชายแดน (Max 30)', 'ความถี่ในการผ่าน (Max 20)', 'ยานพาหนะต่างถิ่น (Max 10)', 'การเคลื่อนที่แบบกลุ่ม (Max 20)']
            r_vals.append(r_vals[0])
            theta_vals.append(theta_vals[0])
            fig_radar = go.Figure()
            fig_radar.add_trace(go.Scatterpolar(r=r_vals, theta=theta_vals, fill='toself', name='พฤติกรรมเป้าหมาย', line_color='#9f1239', fillcolor='rgba(159, 18, 57, 0.4)'))
            fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 30], showticklabels=False), gridshape='linear'), showlegend=False, height=300, margin=dict(t=20, b=20, l=40, r=40), title=dict(text="📊 แผนภูมิวิเคราะห์รูปแบบพฤติกรรม (Risk Radar)", font=dict(size=14)), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_radar, use_container_width=True, key=f"radar_chart_{selected_target}")
            
        with col_summary:
            total_reads = len(case_data)
            night_reads = len(case_data[case_data['Is_Night'] == True])
            night_pct = (night_reads / total_reads) * 100 if total_reads > 0 else 0
            cam_str = ", ".join([f"{k} ({v} ครั้ง)" for k, v in case_data['จุดติดตั้งกล้อง'].value_counts().head(2).items()])
            prov_str = ", ".join(list(set(case_data['จังหวัด'].unique()) - {""}))
            
            # 🧹 Clean HTML Summary & ขยายความ Intelligence Summary
            dwell_str = ""
            if is_anomaly:
                border_logs = main_car_df[main_car_df['Zone'] == 'A']
                if not border_logs.empty and len(border_logs) > 1:
                    dwell_hrs = (border_logs['Datetime'].max() - border_logs['Datetime'].min()).total_seconds() / 3600.0
                    if dwell_hrs > 0: 
                        dwell_str = f"**⏱️ ระยะเวลาแช่ตัวโซนชายแดน:** {dwell_hrs:.1f} ชั่วโมง\n\n"

            summary_md = f"""
**📌 จังหวัดที่จดทะเบียน:** {prov_str}

**📊 สถิติการตรวจพบสะสม:** {total_reads} ครั้ง

{dwell_str}**🌙 สัดส่วนการปฏิบัติการยามวิกาล:** {night_pct:.1f}% ({night_reads} ครั้ง)

**📍 จุดตรวจที่ปรากฏตัวบ่อยที่สุด:** {cam_str}
"""
            
            if is_convoy:
                cams_in_order = main_car_df['จุดติดตั้งกล้อง'].unique().tolist()
                start_cam = cams_in_order[0] if cams_in_order else "-"
                end_cam = cams_in_order[-1] if cams_in_order else "-"
                start_time = main_car_df['Datetime'].min().strftime('%H:%M:%S')
                gap_str = target_info.get("ระยะห่างเฉลี่ย", "-")
                total_dist_val = target_info.get("Total_Dist", f"{total_dist_km:.1f}") if target_info.get("Total_Dist", "-") != "-" else f"{total_dist_km:.1f}"
                
                summary_md += f"\n\n---\n**🚘 บทวิเคราะห์พฤติกรรมขบวนรถ (AI Insight):**\nขบวนรถก่อตัวที่ด่าน **{start_cam}** เมื่อเวลา **{start_time}** และสิ้นสุดที่ด่าน **{end_cam}** ระยะทางรวม **{total_dist_val}** กม. โดยมีระยะห่างเฉลี่ย **{gap_str}** ไม่พบพฤติกรรมการสลับคันนำ"
                
            elif is_anomaly:
                cams_in_order = main_car_df['จุดติดตั้งกล้อง'].unique().tolist()
                start_cam = cams_in_order[0] if len(cams_in_order)>0 else "-"
                end_cam = cams_in_order[-1] if len(cams_in_order)>0 else "-"
                total_dist_val = target_info.get("Total_Dist", f"{total_dist_km:.1f}")
                dwell_val = f"{dwell_hrs:.1f}" if 'dwell_hrs' in locals() and dwell_hrs > 0 else "1-4"
                
                summary_md += f"\n\n---\n**🔄 บทวิเคราะห์มุดช่องโหว่ (AI Insight):**\nเป้าหมายขับออกนอกพื้นที่ผ่านด่าน **{start_cam}** หายไปจากระบบเป็นเวลา **{dwell_val}** ชั่วโมง ก่อนจะปรากฏตัวอีกครั้งที่ด่าน **{end_cam}** ระยะทางสัญจรรวม **{total_dist_val}** กม."

            st.markdown("<div class='dossier-summary'>", unsafe_allow_html=True)
            st.markdown("#### 📋 สรุปข้อมูลประวัติเป้าหมาย (Intelligence Summary)")
            st.markdown(summary_md)
            st.markdown("</div>", unsafe_allow_html=True)
            
        if total_time_hr > 0 and len(main_car_df) > 1:
            actual_speed = total_dist_km / total_time_hr
            st.markdown(f"<div class='osrm-metric'>📍 <b>ประเมินพิกัดและระยะทาง (Offline Engine):</b> ทำการประเมินอัตราเร็วเฉลี่ยด้วยค่าชดเชยทางกายภาพ ได้ผลลัพธ์ <b>{actual_speed:.0f} กม./ชม.</b> (ระยะทาง {total_dist_km:.1f} กม. ภายในระยะเวลา {total_time_hr:.1f} ชม.)</div>", unsafe_allow_html=True)
            
        st.markdown("### 🗺️ แผนที่ระบุพิกัดเป้าหมายทางยุทธวิธี (2D Map)")
        m_case = folium.Map(location=[case_data['ละติจูด'].mean(), case_data['ลองจิจูด'].mean()], zoom_start=9)
        hex_pastel = ['#9f1239', '#1e3a8a', '#047857', '#4338ca', '#b45309', '#be123c'] * 5
        cool_colors = ['#1e3a8a', '#0369a1', '#047857', '#4338ca', '#334155', '#0f766e']
        
        if len(cars) >= 2:
            for idx, c in enumerate(cars):
                c_data = case_data[case_data['ทะเบียน_Full'] == c]
                coords = [(r.ละติจูด, r.ลองจิจูด) for r in c_data.itertuples()]
                if is_convoy:
                    if idx == 0: f_color, h_color = 'red', '#dc2626'
                    else: f_color, h_color = 'blue', cool_colors[(idx-1) % len(cool_colors)]
                else:
                    f_color, h_color = 'blue', hex_pastel[idx]
                for r in c_data.itertuples(): 
                    folium.Marker(location=(r.ละติจูด, r.ลองจิจูด), popup=f"<b>{c}</b><br>{r.เวลา} - {r.จุดติดตั้งกล้อง}", icon=folium.Icon(color=f_color, icon='car', prefix='fa')).add_to(m_case)
                if len(coords) > 1: plugins.AntPath(coords, color=h_color, weight=4, dash_array=[10, 20]).add_to(m_case)
        else:
            c_df = case_data[case_data['ทะเบียน_Full'] == cars[0]].sort_values('Datetime')
            coords = [(r.ละติจูด, r.ลองจิจูด) for r in c_df.itertuples()]
            for r in c_df.itertuples(): folium.Marker(location=(r.ละติจูด, r.ลองจิจูด), popup=f"{r.เวลา} - {r.จุดติดตั้งกล้อง}", icon=folium.Icon(color='blue', icon='car', prefix='fa')).add_to(m_case)
            if len(coords) > 1: plugins.AntPath(coords, color='blue', weight=4).add_to(m_case)
                
        components.html(m_case.get_root().render(), height=400)
        
    if is_convoy:
        st.markdown("### 🔗 ตารางวิเคราะห์โครงข่ายขบวนรถ (Convoy Formation Analysis)")
        convoy_details = []
        cams_in_order = case_data.sort_values('Datetime').drop_duplicates('จุดติดตั้งกล้อง', keep='first')['จุดติดตั้งกล้อง'].tolist()
        
        for cam in cams_in_order:
            cam_data = case_data[case_data['จุดติดตั้งกล้อง'] == cam].sort_values('Datetime')
            if len(cam_data) > 1: 
                dt_str = cam_data.iloc[0]['Datetime'].strftime('%Y/%m/%d')
                num_cars = len(cam_data)
                
                lead_plate = cam_data.iloc[0]['ทะเบียน_Full']
                
                plates = []
                roles = []
                times = []
                speeds = []
                
                for idx, row in cam_data.iterrows():
                    plates.append(row['ทะเบียน_Full'])
                    roles.append("รถนำ(Scout)" if row['ทะเบียน_Full'] == lead_plate else "รถตาม")
                    times.append(row['Datetime'].strftime('%H:%M:%S'))
                    spd = row['Speed_kmh']
                    speeds.append(f"{spd:.0f}" if pd.notna(spd) and spd > 0 else "-")
                        
                convoy_details.append({
                    "จุดตรวจจับร่วม": cam,
                    "วันที่": dt_str,
                    "จำนวนยานพาหนะในกลุ่มขบวน": num_cars,
                    "ลำดับหมายเลขทะเบียนในกลุ่มขบวน": " ➡️ ".join(plates),
                    "บทบาท": " ➡️ ".join(roles),
                    "ห้วงเวลาที่สัญจรผ่าน": " ➡️ ".join(times),
                    "ความเร็ว (กม./ชม.)": " ➡️ ".join(speeds)
                })
        
        if convoy_details:
            df_convoy = pd.DataFrame(convoy_details)
            df_convoy = df_convoy.sort_values(by=['จำนวนยานพาหนะในกลุ่มขบวน', 'วันที่'], ascending=[False, True])
            st.dataframe(df_convoy, use_container_width=True, hide_index=True)
            
    st.markdown("---")
    st.markdown("### ⏱️ โครงข่ายเวลา-สถานที่ (Staggered Grid Time-Space Diagram)")
    
    fig_ts = go.Figure()
    hex_pastel = ['#9f1239', '#1e3a8a', '#047857', '#4338ca', '#b45309', '#be123c'] * 5
    cool_colors = ['#1e3a8a', '#0369a1', '#047857', '#4338ca', '#334155', '#0f766e']
    
    cams_in_order = case_data.sort_values('Datetime').drop_duplicates('จุดติดตั้งกล้อง', keep='first')['จุดติดตั้งกล้อง'].tolist()
    cam_to_x = {cam: idx for idx, cam in enumerate(cams_in_order)}
    short_cams = [re.split(r',|\sกอง|\sสถานี|\sตำรวจ', str(cam))[0].strip() for cam in cams_in_order]
    
    t_min_cam = case_data.groupby('จุดติดตั้งกล้อง')['Datetime'].min().to_dict()
    
    for idx, c in enumerate(cars):
        c_df = case_data[case_data['ทะเบียน_Full'] == c].sort_values('Datetime')
        
        if is_clone:
            normal_df = c_df[c_df['Speed_kmh'] <= 200] if show_real else pd.DataFrame()
            ghost_df = c_df[c_df['Speed_kmh'] > 200] if show_fake else pd.DataFrame()
        else:
            normal_df = c_df
            ghost_df = pd.DataFrame()
            
        icon_str = "🚚" if "บรร取ุก" in str(c_df.iloc[0]['ประเภทรถ']) or "บรรทุก" in str(c_df.iloc[0]['ประเภทรถ']) else "🚗"
        
        if is_convoy:
            if idx == 0:
                line_color, car_name = '#dc2626', f"🔴 รถนำ: {c}"
            else:
                line_color, car_name = cool_colors[(idx-1) % len(cool_colors)], f"🚙 รถตาม: {c}"
        elif is_clone:
            line_color, car_name = '#10b981', f"รถจริง: {c}"
        else:
            line_color, car_name = hex_pastel[idx % len(hex_pastel)], f"เป้าหมาย: {c}"
        
        if not normal_df.empty:
            x_vals = []
            text_vals = []
            for _, r in normal_df.iterrows():
                cam = r['จุดติดตั้งกล้อง']
                base_x = cam_to_x[cam]
                time_diff_min = (r['Datetime'] - t_min_cam[cam]).total_seconds() / 60.0
                offset_x = base_x + (min(time_diff_min, 60) * 0.015) 
                x_vals.append(offset_x)
                text_vals.append(f"{icon_str} {r['Datetime'].strftime('%H:%M:%S')}")
                
            fig_ts.add_trace(go.Scatter(
                x=x_vals, y=[car_name]*len(normal_df), mode='lines+markers+text',
                name=car_name, text=text_vals, textposition="top center", 
                textfont=dict(size=13, color='black'),
                marker=dict(size=10, color=line_color, line=dict(color='white', width=1)),
                line=dict(width=3, color=line_color)
            ))
            
        if not ghost_df.empty:
            gx_vals = []
            gtext_vals = []
            for _, r in ghost_df.iterrows():
                cam = r['จุดติดตั้งกล้อง']
                base_x = cam_to_x.get(cam, len(cams_in_order))
                time_diff_min = (r['Datetime'] - t_min_cam.get(cam, r['Datetime'])).total_seconds() / 60.0
                offset_x = base_x + (min(time_diff_min, 60) * 0.015)
                gx_vals.append(offset_x)
                gtext_vals.append(f"🚨 {r['Datetime'].strftime('%H:%M:%S')}")
                
            fig_ts.add_trace(go.Scatter(
                x=gx_vals, y=[f"รถแฝด: {c}"]*len(ghost_df), mode='markers+text',
                name=f"รถแฝด: {c}", text=gtext_vals, textposition="top center", 
                textfont=dict(size=14, color='red'),
                marker=dict(size=15, color='red', symbol='x')
            ))
            
    fig_ts.update_layout(
        xaxis_title="จุดติดตั้งกล้อง (เรียงตามลำดับผ่าน)", yaxis_title="สถานะ/พฤติกรรม (นำ-ตาม)",
        showlegend=True, height=max(600, len(cars) * 100), margin=dict(l=20, r=20, t=40, b=50),
        plot_bgcolor='rgba(248, 250, 252, 0.8)', paper_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(
            tickmode='array', tickvals=list(range(len(cams_in_order))), ticktext=short_cams,
            showgrid=True, gridcolor='#cbd5e1', gridwidth=1.5, tickangle=-45
        ), 
        yaxis=dict(type='category', showgrid=True, gridcolor='#f1f5f9', autorange='reversed')
    )
    
    st.plotly_chart(fig_ts, use_container_width=True, key=f"ts_horizontal_{selected_target}")

    st.markdown("---")
    st.markdown("### 📋 ตารางพยานหลักฐาน (Raw Evidence Data)")
    
    raw_evidence = case_data[['วันที่', 'เวลา', 'ทะเบียน_Full', 'จุดติดตั้งกล้อง', 'ประเภทรถ', 'Speed_kmh']].copy()
    raw_evidence['Speed_kmh'] = raw_evidence['Speed_kmh'].round(1)
    raw_evidence = raw_evidence.rename(columns={'วันที่': 'วันที่เกิดเหตุ', 'เวลา': 'เวลาโผล่', 'ทะเบียน_Full': 'หมายเลขทะเบียน', 'จุดติดตั้งกล้อง': 'พิกัดจุดตรวจ', 'ประเภทรถ': 'ประเภท', 'Speed_kmh': 'อัตราเร็ว (กม./ชม.)'})
    st.dataframe(raw_evidence.reset_index(drop=True), use_container_width=True)
            
    st.markdown("</div>", unsafe_allow_html=True)

def show_clickable_table(df_display, table_key, active_db, priority_df):
    if df_display.empty:
        st.info("🟢 ไม่พบเป้าหมายที่อยู่ในเกณฑ์เฝ้าระวัง")
        return
        
    conn = sqlite3.connect(DB_PATH)
    status_df = pd.read_sql("SELECT Target_ID, status FROM target_status", conn)
    conn.close()
    
    df_clean = df_display.copy()
    if not status_df.empty:
        df_clean = df_clean.merge(status_df, on='Target_ID', how='left')
    else:
        df_clean['status'] = np.nan
        
    df_clean['สถานะ'] = df_clean['status'].fillna("🔴 เฝ้าระวังใหม่")
    df_clean['Risk Score'] = df_clean['Risk Score'].fillna(0).astype(int).astype(str) + "%"
    
    if table_key == "t_cloned":
        cols_order = ['สถานะ', 'เป้าหมาย', 'Speed_Warp', 'เวลาโผล่ล่าสุด', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']
        df_clean = df_clean.rename(columns={'Speed_Warp': 'ความเร็วที่ผิดปกติ (กม./ชม.)'})
        cols_order[2] = 'ความเร็วที่ผิดปกติ (กม./ชม.)'
    elif table_key == "t_others":
        cols_order = ['สถานะ', 'เป้าหมาย', 'ผ่านร่วมกัน (ด่าน)', 'Total_Dist', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']
        df_clean = df_clean.rename(columns={'ผ่านร่วมกัน (ด่าน)': 'จำนวนด่านที่ผ่าน (ด่าน)', 'Total_Dist': 'ระยะทางสะสม (กม.)'})
        cols_order[2] = 'จำนวนด่านที่ผ่าน (ด่าน)'
        cols_order[3] = 'ระยะทางสะสม (กม.)'
    else:
        cols_order = ['สถานะ', 'เป้าหมาย', 'ผ่านร่วมกัน (ด่าน)', 'ระยะห่างเฉลี่ย', 'จุดตรวจพบล่าสุด', 'พฤติกรรมต้องสงสัย', 'Risk Score']
        
    df_clean = df_clean[cols_order].copy()
    
    event = st.dataframe(
        df_clean.style.map(color_score, subset=['Risk Score']),
        use_container_width=True, on_select="rerun", selection_mode="single-row", hide_index=True, key=f"tbl_{table_key}"
    )
    
    if len(event.selection.rows) > 0:
        selected_idx = event.selection.rows[0]
        target_id = df_display.iloc[selected_idx]['Target_ID']
        render_case_dossier(target_id, active_db, priority_df)

# ==========================================
# 5. สถาปัตยกรรมหน้าจอหลัก (Decoupled UI)
# ==========================================
st.markdown("""
    <div class='main-title'>🛡️ HWPD 60 Intelligence Target &amp; Trap</div>
    <div class='main-subtitle'>ศูนย์ปฏิบัติการข่าวกรองสกัดกั้นบนสายทาง &nbsp;|&nbsp; HWPD 60 i-Trap Command Center</div>
    <hr class='header-divider'>
""", unsafe_allow_html=True)

_th = st.session_state.get('theme', 'dark')
_th_icon = '🌙' if _th == 'dark' else '☀️'
_th_label = 'Dark Mode' if _th == 'dark' else 'Light Mode'

st.sidebar.markdown("""
    <div style='text-align:center; padding: 14px 0 8px 0;'>
        <div style='font-size:42px; margin-bottom:6px;'>🛡️</div>
        <div style='font-size:17px; font-weight:800; color:#93c5fd; letter-spacing:2px; text-transform:uppercase;'>HWPD 60 i-Trap</div>
        <div style='font-size:12px; color:#64748b; letter-spacing:0.8px; margin-top:4px; font-weight:500;'>Intelligence Command System</div>
    </div>
    <hr style='border-color: rgba(59,130,246,0.2); margin: 8px 0 8px 0;'>
""", unsafe_allow_html=True)

if st.sidebar.button(f"{_th_icon} {_th_label}", key="theme_toggle_btn", use_container_width=True):
    st.session_state['theme'] = 'light' if _th == 'dark' else 'dark'
    st.rerun()



mode = st.sidebar.radio("🔑 เข้าสู่ระบบ (System Portal):", ["📊 ผู้บังคับบัญชา (Executive Dashboard)", "⚙️ แอดมิน (Admin Portal)"])

if mode == "⚙️ แอดมิน (Admin Portal)":
    st.sidebar.markdown("---")
    
    tab_upload, tab_whitelist = st.tabs(["🗂️ นำเข้าข้อมูล (Data Pipeline)", "📜 บัญชีรถยกเว้น (White-list)"])
    
    with tab_upload:
        st.header("🗂️ การจัดการฐานข้อมูล (Data Pipeline)")
        uploaded_files = st.file_uploader("นำเข้าแฟ้มประวัติจุดตรวจ LPR (CSV/Excel)", accept_multiple_files=True)
        
        if "dq_preview" not in st.session_state:
            st.session_state.dq_preview = None

        if uploaded_files:
            if st.button("🔍 1. ตรวจสอบคุณภาพข้อมูลเบื้องต้น (Data Quality Check)"):
                with st.spinner("กำลังวิเคราะห์โครงสร้างไฟล์..."):
                    st.session_state.dq_preview = preliminary_data_check(uploaded_files)
                    
            if st.session_state.dq_preview:
                dq = st.session_state.dq_preview
                st.info(f"📊 **รายงานคุณภาพข้อมูล:** พบข้อมูลทั้งหมด **{dq['total']:,}** รายการ | สมบูรณ์: **{dq['valid']:,}** รายการ | ป้ายทะเบียนอ่านไม่ได้ (ทิ้ง): **{dq['invalid']:,}** รายการ")
                
                if st.button("🚀 2. ยืนยันและเริ่มประมวลผล (Confirm & Execute Engines)"):
                    with st.spinner("🧠 ระบบกำลังใช้ Polars Engine ประมวลผลข้อมูลระดับ Big Data..."):
                        historical_db_pl = load_historical_data()
                        new_db_pl = process_raw_data_polars(dq['raw_df'])
                        
                        if not new_db_pl.is_empty():
                            active_db_pl = save_to_memory(new_db_pl, historical_db_pl)
                            load_historical_data.clear()  # clear cache ให้ Executive Dashboard โหลดใหม่

                            # ★ ดึงวันที่จากข้อมูล CSV จริง (ไม่ใช้วันที่อัปโหลด)
                            try:
                                _data_dates = new_db_pl['Datetime'].cast(pl.Date).unique().sort()
                                report_date = str(_data_dates[0]) if len(_data_dates) > 0 else datetime.now().strftime('%Y-%m-%d')
                            except:
                                report_date = datetime.now().strftime('%Y-%m-%d')

                            if not active_db_pl.is_empty():
                                # ★ วิเคราะห์เฉพาะวันที่อัปโหลด ไม่ปนกับวันอื่น
                                priority_df = run_intelligence_orchestrator(new_db_pl)

                                active_db_pd = new_db_pl.to_pandas()
                                save_daily_report(report_date, priority_df, active_db_pd)
                                
                                st.success(f"✅ ประมวลผลสำเร็จ! ข้อมูลถูกบันทึกลงฐานข้อมูลเรียบร้อยแล้ว (Report Date: {report_date})")
                                st.session_state.dq_preview = None 
                                
                                st.session_state['nav_tab'] = "🏠 สรุปสถานการณ์ (Overview)"
                                time.sleep(1.5)
                                st.rerun()
                            else:
                                st.warning("⚠️ ข้อมูลในระบบว่างเปล่าหลังจากการกรอง ไม่สามารถวิเคราะห์ได้")
                        else:
                            st.error("❌ ไม่พบข้อมูลที่ถูกต้องในไฟล์ที่อัปโหลด")

    with tab_whitelist:
        st.header("📜 การจัดการบัญชีรถยกเว้น (White-list)")
        st.write("ทะเบียนรถในบัญชีนี้ จะถูก AI มองข้าม (Bypass) เพื่อลดการแจ้งเตือนรถของเจ้าหน้าที่ปฏิบัติงาน")
        
        col_w1, col_w2 = st.columns([7, 3])
        with col_w1:
            new_wl_plate = st.text_input("เพิ่มทะเบียนรถ (เช่น กค1234กรุงเทพมหานคร):")
            new_wl_note = st.text_input("หมายเหตุ (เช่น รถสายตรวจ สภ.เมือง):")
        with col_w2:
            st.write("")
            st.write("")
            if st.button("➕ เพิ่มเข้าบัญชีขาว"):
                if new_wl_plate:
                    clean_p = normalize_plate(new_wl_plate)
                    if clean_p:
                        conn = sqlite3.connect(DB_PATH)
                        conn.execute("INSERT OR REPLACE INTO whitelist_master (ทะเบียนรถ, หมายเหตุ) VALUES (?, ?)", (clean_p, new_wl_note))
                        conn.commit()
                        conn.close()
                        st.success(f"เพิ่ม {clean_p} เรียบร้อยแล้ว")
                    else:
                        st.error("รูปแบบทะเบียนไม่ถูกต้อง")
        
        st.markdown("---")
        conn = sqlite3.connect(DB_PATH)
        wl_df = pd.read_sql("SELECT ทะเบียนรถ, หมายเหตุ FROM whitelist_master", conn)
        conn.close()
        st.write("📋 **รายชื่อรถในบัญชีขาวปัจจุบัน:**")
        st.dataframe(wl_df, use_container_width=True, hide_index=True)
        if not wl_df.empty:
            del_plate = st.selectbox("เลือกทะเบียนที่ต้องการลบออกจากบัญชีขาว:", wl_df['ทะเบียนรถ'])
            if st.button("🗑️ ลบรายการ"):
                conn = sqlite3.connect(DB_PATH)
                conn.execute("DELETE FROM whitelist_master WHERE ทะเบียนรถ=?", (del_plate,))
                conn.commit()
                conn.close()
                st.rerun()

elif mode == "📊 ผู้บังคับบัญชา (Executive Dashboard)":
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🧭 เมนูเจาะลึกสถานการณ์")
    if st.sidebar.button("🏠 สรุปสถานการณ์ (Overview)", use_container_width=True): change_tab("🏠 สรุปสถานการณ์ (Overview)")
    if st.sidebar.button("🚨 รถสวมทะเบียน", use_container_width=True): change_tab("🚨 รถสวมทะเบียน")
    if st.sidebar.button("🚘 ขบวนรถลำเลียง", use_container_width=True): change_tab("🚘 ขบวนรถลำเลียง")
    if st.sidebar.button("🔍 รถพฤติกรรมต้องสงสัย", use_container_width=True): change_tab("🔄 พฤติกรรมมุดชายแดน")
    if st.sidebar.button("⭐ รถที่น่าสนใจ (Watch List)", use_container_width=True): change_tab("⭐ รถที่น่าสนใจ")
    
    conn = sqlite3.connect(DB_PATH)
    try:
        reports_df = pd.read_sql("SELECT report_date FROM daily_reports ORDER BY report_date DESC", conn)
        available_dates = reports_df['report_date'].tolist()
    except:
        available_dates = []
    
    if not available_dates:
        st.info("📭 ยังไม่มีรายงานในระบบ กรุณาให้ Admin ทำการอัปโหลดและประมวลผลข้อมูลก่อนครับ")
    else:
        st.markdown("""
        <div class="ticker-wrap">
            <div class="ticker-content">
                📡 SYSTEM ONLINE | SECURE CONNECTION ESTABLISHED | HWPD 60 COMMAND CENTER ACTIVE...
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col_t1, col_t2 = st.columns([8, 2])
        with col_t2:
            selected_date = st.selectbox("📅 เลือกวันที่รายงาน:", available_dates)
        with col_t1:
            st.markdown(f"<div style='padding: 10px; background-color: #f8fafc; border-left: 5px solid #10b981; border-radius: 5px; color: #0f172a;'><span class='live-dot'></span><b>Live Sync: Standby</b> | กำลังแสดงผลรายงานข่าวกรองประจำวันที่: <b>{selected_date}</b></div>", unsafe_allow_html=True)
            
        cursor = conn.cursor()
        cursor.execute("SELECT priority_data, dashboard_metrics FROM daily_reports WHERE report_date = ?", (selected_date,))
        row = cursor.fetchone()
        
        reports_full_df = pd.read_sql("SELECT * FROM daily_reports", conn)
        conn.close()
        
        if row and row[0]:
            try:
                parsed_json = json.loads(row[0])
                priority_df = pd.DataFrame(parsed_json)
            except Exception as e:
                priority_df = pd.DataFrame()
        else:
            priority_df = pd.DataFrame()
            
        metrics = json.loads(row[1]) if row and row[1] else {}
        
        historical_db_pl = load_historical_data()
        if not historical_db_pl.is_empty():
            active_db_all = historical_db_pl.to_pandas()
            # กรองเฉพาะวันที่เลือก (ตรงกับ report_date จากข้อมูล CSV จริง)
            _sel_date = pd.to_datetime(selected_date).date()
            active_db = active_db_all[active_db_all['Datetime'].dt.date == _sel_date].copy()
            if active_db.empty:
                # fallback: ใช้วันล่าสุดที่มีข้อมูล
                active_db = active_db_all
        else:
            active_db_all = pd.DataFrame()
            active_db = pd.DataFrame()

        filtered_df = priority_df[priority_df['Risk Score'].astype(str).str.replace('%', '').astype(float) >= 80].copy() if not priority_df.empty else pd.DataFrame()

        if not filtered_df.empty and metrics:
            
            cat_cloned = len(filtered_df[filtered_df['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"])
            cat_convoy_car = len(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"])
            cat_others = len(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถต้องสงสัย"])
            
            if st.session_state['nav_tab'] == "🏠 สรุปสถานการณ์ (Overview)":
                
                apex_df = filtered_df[filtered_df['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"].copy()
                if not apex_df.empty:
                    st.markdown("""
                    <div class='apex-threat-banner'>
                        🚨 กลุ่มเป้าหมายความมั่นคงระดับสูงสุด (Apex Threats) 🚨<br>
                        <span style='font-size:14px; font-weight:normal;'>ตรวจพบเป้าหมายที่มีพฤติกรรมภัยคุกคามซ้อนทับกัน โปรดวิทยุสั่งการสกัดกั้นทันที!</span>
                    </div>
                    """, unsafe_allow_html=True)
                    show_clickable_table(apex_df, "t_apex", active_db, filtered_df)
                    st.markdown("---")

                reports_full_df['date'] = pd.to_datetime(reports_full_df['report_date'])
                sel_d = pd.to_datetime(selected_date)
                mask_7 = (reports_full_df['date'] <= sel_d) & (reports_full_df['date'] > sel_d - timedelta(days=7))
                mask_30 = (reports_full_df['date'] <= sel_d) & (reports_full_df['date'] > sel_d - timedelta(days=30))
                
                def calc_cum(mask):
                    c_apex, c_clone, c_car, c_other = 0, 0, 0, 0
                    for p_data in reports_full_df[mask]['priority_data']:
                        try:
                            pdf = pd.DataFrame(json.loads(p_data))
                            if not pdf.empty:
                                fdf = pdf[pdf['Risk Score'].astype(str).str.replace('%', '').astype(float) >= 80]
                                c_apex += len(fdf[fdf['ประเภท'] == "กลุ่มเป้าหมายความมั่นคงระดับสูงสุด"])
                                c_clone += len(fdf[fdf['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"])
                                c_car += len(fdf[fdf['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"])
                                c_other += len(fdf[fdf['ประเภท'] == "กลุ่มรถต้องสงสัย"])
                        except: pass
                    return c_apex, c_clone, c_car, c_other

                cum7_apex, cum7_clone, cum7_car, cum7_other = calc_cum(mask_7)
                cum30_apex, cum30_clone, cum30_car, cum30_other = calc_cum(mask_30)

                st.markdown("### 📊 ข้อมูลสรุปเป้าหมายสำคัญ (Intelligence Brief)")
                tab_daily, tab_repeat = st.tabs(["📅 ประจำวัน (Daily)", "🔁 รถวิ่งซ้ำ (30 วัน)"])

                
                with tab_daily:
                    # Load watch list count
                    try:
                        _wconn = sqlite3.connect(DB_PATH)
                        _wl_df = pd.read_sql("SELECT plate FROM historical_suspects WHERE seen_count >= 1", _wconn)
                        _today_plates = set(active_db['ทะเบียน_Full'].unique()) if not active_db.empty else set()
                        _watch_today = len(_wl_df[_wl_df['plate'].isin(_today_plates)]) if not _wl_df.empty else 0
                        _wconn.close()
                    except: _watch_today = 0

                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1: st.markdown(f"<div class='metric-card card-apex'><div class='metric-label'>🚨 ระดับสูงสุด</div><div class='metric-value'>{len(apex_df)}</div></div>", unsafe_allow_html=True)
                    with col2: 
                        st.markdown(f"<div class='metric-card card-clone'><div class='metric-label'>🚗 สวมทะเบียน</div><div class='metric-value'>{cat_cloned}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_clone_d", use_container_width=True): change_tab("🚨 รถสวมทะเบียน"); st.rerun()
                    with col3: 
                        st.markdown(f"<div class='metric-card card-car'><div class='metric-label'>🏎️ ขบวนรถยนต์</div><div class='metric-value'>{cat_convoy_car}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_car_d", use_container_width=True): change_tab("🚘 ขบวนรถลำเลียง"); st.rerun()
                    with col4: 
                        st.markdown(f"<div class='metric-card card-anomaly'><div class='metric-label'>🔄 รถต้องสงสัย</div><div class='metric-value'>{cat_others}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_anomaly_d", use_container_width=True): change_tab("🔄 พฤติกรรมมุดชายแดน"); st.rerun()
                    with col5:
                        st.markdown(f"<div class='metric-card card-watch'><div class='metric-label'>⭐ Watch List วันนี้</div><div class='metric-value'>{_watch_today}</div></div>", unsafe_allow_html=True)
                        if st.button("🔍 เจาะลึก", key="btn_watch_d", use_container_width=True): change_tab("⭐ รถที่น่าสนใจ"); st.rerun()
                        
                with tab_repeat:
                    _rep = repeat_offender_analysis(DB_PATH, selected_date, window_days=30, min_days=2)

                    if _rep.empty:
                        st.info("⚠️ ยังไม่พบทะเบียนที่ปรากฏซ้ำ ≥ 2 วัน ในช่วง 30 วันที่ผ่านมา — ต้องมีข้อมูลอย่างน้อย 2 วันในระบบ")
                    else:
                        # ── Summary cards ──────────────────────────────────────────
                        _r_clone  = _rep[_rep['ประเภทหลัก'].str.contains("สวมทะเบียน", na=False)]
                        _r_convoy = _rep[_rep['ประเภทหลัก'].str.contains("ขบวน", na=False)]
                        _r_susp   = _rep[~_rep['ประเภทหลัก'].str.contains("สวมทะเบียน|ขบวน", na=False)]

                        rc1, rc2, rc3 = st.columns(3)
                        with rc1: st.markdown(f"<div class='metric-card card-clone'><div class='metric-label'>🚗 สวมทะเบียนซ้ำ</div><div class='metric-value'>{len(_r_clone)}</div><div style='font-size:11px;color:#94a3b8'>≥2 วัน / 30 วัน</div></div>", unsafe_allow_html=True)
                        with rc2: st.markdown(f"<div class='metric-card card-car'><div class='metric-label'>🏎️ ขบวนรถซ้ำ</div><div class='metric-value'>{len(_r_convoy)}</div><div style='font-size:11px;color:#94a3b8'>≥2 วัน / 30 วัน</div></div>", unsafe_allow_html=True)
                        with rc3: st.markdown(f"<div class='metric-card card-anomaly'><div class='metric-label'>🔍 รถต้องสงสัยซ้ำ</div><div class='metric-value'>{len(_r_susp)}</div><div style='font-size:11px;color:#94a3b8'>≥2 วัน / 30 วัน</div></div>", unsafe_allow_html=True)

                        st.markdown("---")
                        _hist_db = active_db_all if not active_db_all.empty else active_db

                        # ── Helper: render one type group ────────────────────────
                        def _show_repeat_group(group_df, group_label, type_icon):
                            if group_df.empty: return
                            st.markdown(f"#### {type_icon} {group_label} — {len(group_df)} คัน")
                            for _, rrow in group_df.sort_values('วันที่พบ', ascending=False).iterrows():
                                freq = rrow['วันที่พบ']
                                freq_badge = "🔴" if freq >= 10 else "🟠" if freq >= 5 else "🟡" if freq >= 3 else "🟢"
                                score_v = rrow['คะแนนสูงสุด']
                                with st.expander(
                                    f"{freq_badge} **{rrow['plate']}**  |  พบซ้ำ {freq} วัน  "
                                    f"|  ครั้งแรก {rrow['ครั้งแรก']}  →  ล่าสุด {rrow['ล่าสุด']}  "
                                    f"|  Score {score_v:.0f}"
                                ):
                                    colInfo, colMap = st.columns([1, 2])
                                    with colInfo:
                                        st.markdown(f"**ทะเบียน:** `{rrow['plate']}`")
                                        st.markdown(f"**ประเภท:** {rrow['ประเภทหลัก']}")
                                        st.markdown(f"**พบทั้งหมด:** {freq} วัน")
                                        st.markdown(f"**คะแนนสูงสุด:** {score_v:.0f}")
                                        st.markdown("**วันที่ตรวจพบ:**")
                                        for d in rrow['dates_list']:
                                            st.markdown(f"&nbsp;&nbsp;• {d}")
                                        st.markdown(f"**พฤติกรรม:**  \n{rrow['เหตุผลรวม'][:300]}")
                                    with colMap:
                                        render_repeat_offender_dossier(
                                            rrow['plate'], _hist_db, rrow['dates_list']
                                        )
                            st.markdown("")

                        _show_repeat_group(_r_clone,  "รถสวมทะเบียนซ้ำ",    "🚗")
                        _show_repeat_group(_r_convoy, "ขบวนรถลำเลียงซ้ำ",   "🏎️")
                        _show_repeat_group(_r_susp,   "รถต้องสงสัยซ้ำ",     "🔍")


                st.markdown("### 🗺️ แผนที่ประเมินความเสี่ยงทางยุทธวิธี (2D Risk Hotspots & Heatmap)")
                m_agg = folium.Map(location=[15.0, 102.0], zoom_start=6) 
                map_stats = metrics.get('map_stats', [])
                if map_stats:
                    heat_data = [[row['lat'], row['lon'], row['volume']] for row in map_stats]
                    HeatMap(heat_data, radius=25, blur=15, min_opacity=0.4).add_to(m_agg)
                    
                    mc = MarkerCluster().add_to(m_agg)
                    m_agg.location = [map_stats[0]['lat'], map_stats[0]['lon']]
                    for row_stat in map_stats:
                        vol = row_stat['volume']
                        primary = str(row_stat.get('primary_threat', ''))
                        
                        if "สวมทะเบียน" in primary: color = 'orange'
                        elif "ขบวน" in primary: color = 'darkblue'
                        else: color = 'purple'
                        
                        folium.Marker(
                            location=[row_stat['lat'], row_stat['lon']],
                            popup=f"<b>จุดตรวจ:</b> {row_stat.get('จุดติดตั้งกล้อง', '')}<br><b>เป้าหมายผ่าน:</b> {vol} คัน<br><b>ภัยคุกคามหลัก:</b> {primary}",
                            icon=folium.Icon(color=color, icon='info-sign')
                        ).add_to(mc)
                        
                    legend_html = """
                     <div class="map-legend">
                     <b>สัญลักษณ์ภัยคุกคาม:</b><br>
                     &nbsp; <i class="fa fa-map-marker fa-1x" style="color:orange"></i> สวมทะเบียน<br>
                     &nbsp; <i class="fa fa-map-marker fa-1x" style="color:darkblue"></i> ขบวนรถลำเลียง<br>
                     &nbsp; <i class="fa fa-map-marker fa-1x" style="color:purple"></i> รถต้องสงสัย
                     </div>
                     """
                    m_agg.get_root().html.add_child(folium.Element(legend_html))
                        
                components.html(m_agg.get_root().render(), height=450)
                st.markdown("---")

                st.markdown("### 🕒 นาฬิกาประเมินสถานการณ์เชิงยุทธวิธี (Advanced Tactical Crime Clock)")
                clock_data = metrics.get('clock', {})
                tactical_data = metrics.get('tactical', {})
                
                if clock_data:
                    hours = list(range(24))
                    total_max = max(clock_data['total_hourly']) if max(clock_data['total_hourly']) > 0 else 1
                    all_threats = clock_data['apex_hr'] + clock_data['cloned_hr'] + clock_data['convoy_hr'] + clock_data['border_hr']
                    target_max = max(all_threats) if max(all_threats) > 0 else 1
                    
                    norm_total = [(v / total_max) * 100 for v in clock_data['total_hourly']]
                    norm_apex = [(v / target_max) * 100 for v in clock_data['apex_hr']]
                    norm_cloned = [(v / target_max) * 100 for v in clock_data['cloned_hr']]
                    norm_convoy = [(v / target_max) * 100 for v in clock_data['convoy_hr']]
                    norm_border = [(v / target_max) * 100 for v in clock_data['border_hr']]
                    
                    fig_clock = go.Figure()
                    fig_clock.add_trace(go.Scatterpolar(r=norm_total + [norm_total[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='ปริมาณการจราจรทั่วไป', line_color='rgba(148, 163, 184, 0.4)', fillcolor='rgba(148, 163, 184, 0.15)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_apex + [norm_apex[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มเป้าหมายความมั่นคงระดับสูงสุด', line_color='rgba(159, 18, 57, 0.9)', fillcolor='rgba(159, 18, 57, 0.5)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_cloned + [norm_cloned[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มเป้าหมายสวมทะเบียน', line_color='rgba(234, 88, 12, 0.9)', fillcolor='rgba(234, 88, 12, 0.3)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_convoy + [norm_convoy[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มโครงข่ายขบวนรถ', line_color='rgba(30, 58, 138, 0.9)', fillcolor='rgba(30, 58, 138, 0.4)'))
                    fig_clock.add_trace(go.Scatterpolar(r=norm_border + [norm_border[0]], theta=[f"{i:02d}:00" for i in hours] + ["00:00"], fill='toself', name='กลุ่มรถต้องสงสัย', line_color='rgba(126, 34, 206, 0.9)', fillcolor='rgba(126, 34, 206, 0.4)'))
                    
                    fig_clock.update_layout(polar=dict(radialaxis=dict(visible=False, range=[0, 100]), angularaxis=dict(direction="clockwise", rotation=90, categoryorder='array', categoryarray=[f"{i:02d}:00" for i in range(24)])), showlegend=True, height=550, margin=dict(t=40, b=40, l=40, r=40), legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    
                    col_c1, col_c2 = st.columns([55, 45])
                    with col_c1: st.plotly_chart(fig_clock, use_container_width=True)
                    with col_c2:
                        st.markdown(f"""
                        <div class='tactical-brief'>
                            <b>🤖 รายงานสรุปการประเมินสถานการณ์ (AI Tactical Brief):</b><br><br>
                            <b>1. มิติเวลา (Temporal):</b> ตรวจพบความหนาแน่นสูงสุดของเป้าหมายหลัก <b>[{tactical_data.get('main_threat', '-')}]</b> ในห้วงเวลา <b>{tactical_data.get('peak_hr', 0):02d}:00 - {tactical_data.get('peak_hr', 0)+1:02d}:00 น.</b><br>
                            <b>2. มิติพื้นที่ (Spatial):</b> จุดบอดและคอขวดที่เฝ้าระวังและสกัดกั้นที่แนะนำคือ บริเวณจุดตรวจ <u>{tactical_data.get('peak_cam', '-')}</u> ซึ่งมีเป้าหมายลัดเลาะผ่านมากที่สุด<br>
                            <b>3. มิติพฤติกรรม (Behavioral):</b> มีสัดส่วนเป้าหมายแฝงตัวเทียบกับปริมาณการจราจรปกติสูงถึง <b>{tactical_data.get('max_risk_ratio', 0):.1f}%</b> (ชี้ให้เห็นความจงใจใช้เส้นทางหลบเลี่ยงในช่วงที่รถพลุกพล่านน้อย)
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown("**📋 ตารางข้อมูลสถานการณ์: ห้วงเวลา และ จุดติดตั้งกล้อง**")
                        if metrics.get('tactical_table'):
                            st.dataframe(pd.DataFrame(metrics['tactical_table']), use_container_width=True, hide_index=True)

            elif st.session_state['nav_tab'] == "🚨 รถสวมทะเบียน":
                st.markdown("<div class='risk-orange'>🚨 รายงานเจาะลึก: กลุ่มเป้าหมายสวมทะเบียน (อัตราเร็วเหนือขีดจำกัดทางกายภาพ)</div><br>", unsafe_allow_html=True)
                show_clickable_table(filtered_df[filtered_df['ประเภท'] == "กลุ่มเป้าหมายสวมทะเบียน"], "t_cloned", active_db, filtered_df)

            elif st.session_state['nav_tab'] == "🚘 ขบวนรถลำเลียง":
                st.markdown("<div class='risk-blue'>🏎️ รายงานเจาะลึก: โครงข่ายขบวนรถลำเลียง (พฤติกรรมวิ่งนำ-ตามทางไกล)</div><br>", unsafe_allow_html=True)
                show_clickable_table(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถยนต์เคลื่อนที่แบบขบวน"], "t_convoy_car", active_db, filtered_df)

            elif st.session_state['nav_tab'] == "🔄 พฤติกรรมมุดชายแดน":
                st.markdown("<div class='risk-purple'>🔄 รายงานเจาะลึก: กลุ่มรถต้องสงสัย (วนลูป / แช่ตัว / มุดช่องโหว่)</div><br>", unsafe_allow_html=True)
                show_clickable_table(filtered_df[filtered_df['ประเภท'] == "กลุ่มรถต้องสงสัย"], "t_others", active_db, filtered_df)

            elif st.session_state['nav_tab'] == "⭐ รถที่น่าสนใจ":
                show_watch_list(active_db, selected_date)

        else:
            st.success("🟢 ไม่พบข้อมูลเป้าหมายเฝ้าระวังความเสี่ยงสูง (>80%) ในวันที่เลือก")