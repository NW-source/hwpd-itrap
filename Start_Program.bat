@echo off
chcp 65001 >nul
title HWPD 60 i-Trap — Setup & Start
color 0B

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║       🛡️  HWPD 60 i-Trap Intelligence System         ║
echo  ║              Setup and Launch Script                 ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: ── 1. ตรวจสอบ Python ──────────────────────────────────────────────────────────
echo [1/5] ตรวจสอบ Python...
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo.
    echo  ❌ ไม่พบ Python กรุณาติดตั้งที่ https://www.python.org/downloads/
    echo     เลือก "Add Python to PATH" ด้วย
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo  ✅ %%i

:: ── 2. ตรวจสอบ pip ─────────────────────────────────────────────────────────────
echo [2/5] ตรวจสอบ pip...
python -m pip --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo  📥 กำลังติดตั้ง pip...
    python -m ensurepip --upgrade
)
echo  ✅ pip พร้อม

:: ── 3. ติดตั้ง Dependencies ────────────────────────────────────────────────────
echo [3/5] ติดตั้ง/อัปเดต Dependencies...
echo  (ครั้งแรกอาจใช้เวลา 2-5 นาที)
echo.
python -m pip install -r requirements.txt --quiet --upgrade
IF ERRORLEVEL 1 (
    echo.
    echo  ⚠️  ติดตั้งบาง package ไม่สำเร็จ กำลังลองใหม่...
    python -m pip install -r requirements.txt
)
echo  ✅ Dependencies ครบแล้ว

:: ── 4. ตรวจสอบ secrets.toml ────────────────────────────────────────────────────
echo [4/5] ตรวจสอบการตั้งค่า Supabase...
IF NOT EXIST ".streamlit\secrets.toml" (
    echo.
    echo  ⚠️  ไม่พบไฟล์ .streamlit\secrets.toml
    echo  กำลังสร้างไฟล์ template...
    
    IF NOT EXIST ".streamlit" mkdir .streamlit
    
    (
        echo [supabase]
        echo url = "https://YOUR_PROJECT.supabase.co"
        echo key = "your-anon-key-here"
    ) > .streamlit\secrets.toml
    
    echo.
    echo  📝 กรุณาแก้ไขไฟล์ .streamlit\secrets.toml
    echo     ใส่ Supabase URL และ Key ของคุณก่อนใช้งาน
    echo.
    echo  เปิดไฟล์ secrets.toml ให้แก้ไขตอนนี้...
    notepad .streamlit\secrets.toml
    echo.
    echo  หลังแก้ไขแล้ว กด Enter เพื่อเริ่มโปรแกรม
    pause
) ELSE (
    echo  ✅ พบไฟล์ secrets.toml แล้ว
)

:: ── 5. เริ่มโปรแกรม ─────────────────────────────────────────────────────────────
echo [5/5] กำลังเปิดระบบ HWPD i-Trap...
echo.
echo  ┌────────────────────────────────────────┐
echo  │  🌐 เปิด Browser ที่: http://localhost:8501  │
echo  │  🔴 กด Ctrl+C เพื่อปิดโปรแกรม          │
echo  └────────────────────────────────────────┘
echo.

:: รอ 2 วิ แล้วเปิด browser อัตโนมัติ
timeout /t 2 /nobreak >nul
start "" "http://localhost:8501"

python -m streamlit run app.py --server.port=8501 --browser.gatherUsageStats=false

echo.
echo  ⏹️  โปรแกรมหยุดทำงานแล้ว
pause