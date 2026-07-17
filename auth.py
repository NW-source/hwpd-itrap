"""
auth.py — ระบบ Login และ Role Management สำหรับ HWPD i-Trap
"""
import hashlib
import secrets
import streamlit as st
from typing import Optional

# ─── Password Hashing ─────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt.encode('utf-8'), 200_000
    ).hex()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hashed = stored_hash.split(':', 1)
        check = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt.encode('utf-8'), 200_000
        ).hex()
        return secrets.compare_digest(check, hashed)
    except Exception:
        return False

# ─── Supabase User Operations ─────────────────────────────────────────────────
def get_user(username: str) -> Optional[dict]:
    """ดึงข้อมูล User จาก Supabase"""
    try:
        from supabase_sync import get_supabase_client
        client = get_supabase_client()
        result = client.table('users').select('*').eq('username', username).eq('is_active', True).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        st.session_state['_auth_error'] = str(e)
        return None

def update_last_login(username: str):
    try:
        from supabase_sync import get_supabase_client
        from datetime import datetime
        client = get_supabase_client()
        client.table('users').update({'last_login': datetime.now().isoformat()}).eq('username', username).execute()
    except Exception:
        pass

def create_user(username: str, password: str, role: str, display_name: str) -> bool:
    """สร้าง User ใหม่ (เฉพาะ super_admin)"""
    try:
        from supabase_sync import get_supabase_client
        client = get_supabase_client()
        client.table('users').insert({
            'username': username,
            'password_hash': hash_password(password),
            'role': role,
            'display_name': display_name,
            'is_active': True
        }).execute()
        return True
    except Exception as e:
        st.error(f"❌ สร้าง User ไม่สำเร็จ: {e}")
        return False

def update_user_password(username: str, new_password: str) -> bool:
    try:
        from supabase_sync import get_supabase_client
        client = get_supabase_client()
        client.table('users').update({
            'password_hash': hash_password(new_password)
        }).eq('username', username).execute()
        return True
    except Exception:
        return False

def deactivate_user(username: str) -> bool:
    try:
        from supabase_sync import get_supabase_client
        client = get_supabase_client()
        client.table('users').update({'is_active': False}).eq('username', username).execute()
        return True
    except Exception:
        return False

def get_all_users() -> list:
    try:
        from supabase_sync import get_supabase_client
        client = get_supabase_client()
        result = client.table('users').select('id,username,role,display_name,is_active,created_at,last_login').order('created_at').execute()
        return result.data or []
    except Exception:
        return []

# ─── Session Management ───────────────────────────────────────────────────────
def get_current_user() -> Optional[dict]:
    return st.session_state.get('current_user', None)

def is_logged_in() -> bool:
    return get_current_user() is not None

def has_role(*roles) -> bool:
    user = get_current_user()
    return user is not None and user.get('role') in roles

def logout():
    st.session_state.pop('current_user', None)
    st.session_state.pop('_auth_error', None)

# ─── Login UI ─────────────────────────────────────────────────────────────────
ROLE_LABEL = {
    'super_admin': '👑 ผู้ดูแลระบบสูงสุด',
    'admin':       '🔧 แอดมิน (Upload ข้อมูล)',
    'viewer':      '👁️ ผู้ดูผล',
}

def render_login_page():
    """แสดงหน้า Login — เรียกก่อน UI หลัก"""
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;500;600;700;800&display=swap');
    html, body, .stApp, [class*="css"] {
        font-family: 'Sarabun', 'TH Sarabun PSK', 'TH Sarabun New', sans-serif !important;
        font-size: 16px !important;
    }
    .login-wrap {
        max-width: 420px; margin: 60px auto 0; padding: 40px 36px;
        background: rgba(15,23,42,0.85); border-radius: 20px;
        border: 1px solid rgba(99,102,241,0.3);
        box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }
    .login-title { font-size:22px; font-weight:800; color:#93c5fd;
        text-align:center; margin-bottom:4px; }
    .login-sub   { font-size:14px; color:#64748b; text-align:center; margin-bottom:28px; }
    </style>
    """, unsafe_allow_html=True)


    col = st.columns([1, 2, 1])[1]
    with col:
        # Logo
        import os
        logo = os.path.join(os.path.dirname(__file__), 'logo.jpeg')
        if os.path.exists(logo):
            st.image(logo, use_container_width=True)

        st.markdown("<div class='login-title'>🛡️ HWPD i-Trap</div>", unsafe_allow_html=True)
        st.markdown("<div class='login-sub'>Intelligence Command System — กรุณาเข้าสู่ระบบ</div>", unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("👤 ชื่อผู้ใช้ (Username)", placeholder="เช่น admin01")
            password = st.text_input("🔑 รหัสผ่าน (Password)", type="password")
            submitted = st.form_submit_button("🔓 เข้าสู่ระบบ", use_container_width=True, type="primary")

        if submitted:
            if not username or not password:
                st.error("กรุณากรอก Username และ Password")
                return

            with st.spinner("กำลังตรวจสอบ..."):
                user = get_user(username.strip().lower())

            if user and verify_password(password, user['password_hash']):
                st.session_state['current_user'] = user
                update_last_login(username.strip().lower())
                role_label = ROLE_LABEL.get(user['role'], user['role'])
                st.success(f"✅ ยินดีต้อนรับ {user.get('display_name', username)} — {role_label}")
                st.rerun()
            else:
                st.error("❌ Username หรือ Password ไม่ถูกต้อง")

        # Debug error
        if '_auth_error' in st.session_state:
            st.caption(f"⚠️ System: {st.session_state.pop('_auth_error')}")

# ─── Role Guard Helpers ───────────────────────────────────────────────────────
def require_login():
    """เรียกที่ต้นไฟล์ — ถ้ายังไม่ login จะแสดงหน้า login แล้วหยุด"""
    if not is_logged_in():
        render_login_page()
        st.stop()

def require_role(*roles):
    """เรียกก่อน section ที่ต้องการสิทธิ์เฉพาะ"""
    if not has_role(*roles):
        st.warning("🚫 ไม่มีสิทธิ์เข้าถึงส่วนนี้")
        st.stop()
