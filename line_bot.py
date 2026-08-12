"""
line_bot.py - HWPD i-Trap LINE Messaging API Bot
=================================================
หน้าที่:
  1. รับ Webhook จาก LINE เมื่อมีคนพิมพ์ทะเบียนในกลุ่ม
  2. ค้นหาข้อมูลจาก SQLite + Parquet
  3. ตอบกลับด้วย Flex Message พร้อมลิงก์แผนที่ Google Maps

ติดตั้ง:
  pip install line-bot-sdk fastapi uvicorn

รัน:
  uvicorn line_bot:app --host 0.0.0.0 --port 8080

ตั้งค่า LINE Webhook URL ใน LINE Developers Console:
  https://<ORACLE_PUBLIC_IP>:8080/webhook
"""
import os, re, sqlite3, json, logging
from datetime import datetime
from typing import Optional
import pandas as pd
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

try:
    from linebot.v3 import WebhookHandler
    from linebot.v3.messaging import (
        ApiClient, Configuration, MessagingApi,
        ReplyMessageRequest, FlexMessage, FlexContainer, TextMessage,
    )
    from linebot.v3.webhooks import MessageEvent, TextMessageContent
    from linebot.v3.exceptions import InvalidSignatureError
    _LINE_SDK_OK = True
except ImportError:
    _LINE_SDK_OK = False
    logging.warning("line-bot-sdk not installed. Run: pip install line-bot-sdk")

# ── Config ────────────────────────────────────────────────────────────────────
CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET       = os.environ.get("LINE_CHANNEL_SECRET", "")
DATA_DIR   = os.environ.get("ITRAP_DATA_DIR", r"D:\itrap_agent")
DB_PATH    = os.path.join(DATA_DIR, "hwpd_master_database.db")
PARQUET_PATH = os.path.join(DATA_DIR, "hwpd_master_data.parquet")
ITRAP_HOST = os.environ.get("ITRAP_HOST", "localhost")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("itrap-linebot")

app = FastAPI(title="HWPD i-Trap LINE Bot", docs_url=None)

if _LINE_SDK_OK and CHANNEL_SECRET:
    handler  = WebhookHandler(CHANNEL_SECRET)
    line_cfg = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
else:
    handler  = None
    line_cfg = None

# ── Plate Detection ───────────────────────────────────────────────────────────
_PLATE_RE = re.compile(r'([ก-ฮ\d]{1,3}\s*[ก-ฮ]{1,2}\s*\d{1,4})\s*([ก-ฮ]+\w*)?')

def normalize_plate(raw: str) -> Optional[str]:
    raw = raw.strip()
    m = _PLATE_RE.search(raw)
    return m.group(0).strip() if m else None

def is_plate_query(text: str) -> bool:
    t = text.strip()
    if re.search(r'[ก-ฮ]', t) and re.search(r'\d{3,4}', t):
        return True
    if re.match(r'^[789]\d[-\s]\d{4}', t):
        return True
    return False

# ── Database Query ────────────────────────────────────────────────────────────
def query_plate(plate_query: str) -> dict:
    result = {
        "found": False, "plate": plate_query,
        "records": 0, "risk_score": 0, "threat_type": "ไม่ระบุ",
        "provinces": [], "cameras": [], "first_seen": "-", "last_seen": "-",
        "lat": None, "lon": None, "status": "ไม่พบในระบบ",
        "is_watchlist": False, "is_whitelist": False, "whitelist_note": "",
    }

    # 1) Whitelist check
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        wl = conn.execute(
            "SELECT หมายเหตุ FROM whitelist_master WHERE ทะเบียนรถ LIKE ?",
            (f"%{plate_query}%",)
        ).fetchone()
        conn.close()
        if wl:
            result["is_whitelist"] = True
            result["whitelist_note"] = f"อยู่ใน Whitelist: {wl[0] or '-'}"
    except Exception as e:
        log.warning(f"whitelist: {e}")

    # 2) Target status
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        ts = conn.execute(
            "SELECT status FROM target_status WHERE Target_ID LIKE ?",
            (f"%{plate_query}%",)
        ).fetchone()
        conn.close()
        if ts:
            result["status"] = ts[0]
    except Exception as e:
        log.warning(f"target_status: {e}")

    # 3) Historical suspects (risk + threat)
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        hs = conn.execute(
            "SELECT threat_type, max_risk_score FROM historical_suspects WHERE plate LIKE ?",
            (f"%{plate_query}%",)
        ).fetchone()
        conn.close()
        if hs:
            result["threat_type"]  = hs[0] or "ไม่ระบุ"
            result["risk_score"]   = hs[1] or 0
            result["is_watchlist"] = True
    except Exception as e:
        log.warning(f"historical_suspects: {e}")

    # 4) Parquet master data
    try:
        import polars as pl
        if os.path.exists(PARQUET_PATH):
            df = pl.scan_parquet(PARQUET_PATH).filter(
                pl.col("ทะเบียน_Full").str.contains(plate_query, literal=True)
            ).collect()
            if not df.is_empty():
                result["found"]   = True
                result["records"] = len(df)
                if "ละติจูด" in df.columns:
                    lr = df.sort("Datetime").tail(1)
                    result["lat"] = float(lr["ละติจูด"][0])
                    result["lon"] = float(lr["ลองจิจูด"][0])
                if "จังหวัด" in df.columns:
                    result["provinces"] = df["จังหวัด"].drop_nulls().unique().to_list()[:4]
                if "จุดติดตั้งกล้อง" in df.columns:
                    vc = df["จุดติดตั้งกล้อง"].drop_nulls().value_counts().sort("count", descending=True)
                    result["cameras"] = [
                        f"{r['จุดติดตั้งกล้อง']} ({r['count']} ครั้ง)"
                        for r in vc.head(3).to_dicts()
                    ]
                if "Datetime" in df.columns:
                    ds = df.sort("Datetime")
                    result["first_seen"] = str(ds["Datetime"].head(1)[0])[:16]
                    result["last_seen"]  = str(ds["Datetime"].tail(1)[0])[:16]
    except Exception as e:
        log.warning(f"parquet: {e}")

    return result

# ── Flex Message Builder ──────────────────────────────────────────────────────
def build_flex(data: dict) -> dict:
    plate = data["plate"]
    color = "#dc2626" if data["risk_score"] >= 80 else ("#f59e0b" if data["risk_score"] >= 50 else "#10b981")
    map_url = (
        f"https://www.google.com/maps?q={data['lat']},{data['lon']}"
        if data["lat"] and data["lon"] else ""
    )

    rows = []
    if data["found"]:
        rows += [
            _row("📊 พบข้อมูล", f"{data['records']:,} รายการ"),
            _row("⚠️ ประเภทภัย", data["threat_type"], color),
            _row("🎯 Risk Score", str(data["risk_score"]), color, bold=True),
        ]
        if data["provinces"]:
            rows.append(_row("📍 จังหวัด", ", ".join(data["provinces"])))
        for cam in data["cameras"]:
            rows.append(_row("📷", cam, "#cbd5e1", size="xs"))
        rows.append(_row("🕐 พบล่าสุด", data["last_seen"]))
    else:
        rows.append({"type": "text", "text": "❌ ไม่พบในฐานข้อมูล", "color": "#94a3b8", "size": "sm", "margin": "sm"})

    if data["is_whitelist"]:
        rows.append({"type": "text", "text": f"✅ {data['whitelist_note']}", "color": "#6ee7b7", "size": "xs", "margin": "sm"})
    if data["is_watchlist"] and not data["is_whitelist"]:
        rows.append({"type": "text", "text": f"🚨 อยู่ใน Watchlist", "color": "#f87171", "size": "xs", "weight": "bold", "margin": "sm"})

    rows.append({"type": "separator", "margin": "sm"})
    rows.append({"type": "text", "text": f"สถานะ: {data['status']}", "color": "#60a5fa", "size": "xs"})

    footer = []
    if map_url:
        footer.append({"type": "button", "style": "primary", "color": "#1d4ed8", "height": "sm",
                        "action": {"type": "uri", "label": "🗺️ ดูแผนที่พิกัดล่าสุด", "uri": map_url}})
    footer.append({"type": "button", "style": "secondary", "height": "sm",
                   "action": {"type": "uri", "label": "🔍 เปิด i-Trap Dashboard",
                              "uri": f"http://{ITRAP_HOST}:8501"}})

    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical", "backgroundColor": "#0f172a", "paddingAll": "14px",
            "contents": [
                {"type": "text", "text": "🛡️ HWPD i-Trap Intelligence", "size": "xs", "color": "#94a3b8", "weight": "bold"},
                {"type": "text", "text": plate, "size": "xl", "weight": "bold", "color": "#f1f5f9"},
            ]
        },
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": "#1e293b",
            "paddingAll": "14px", "spacing": "xs", "contents": rows,
        },
        "footer": {
            "type": "box", "layout": "vertical", "backgroundColor": "#0f172a",
            "paddingAll": "10px", "spacing": "sm", "contents": footer,
        },
    }

def _row(label: str, value: str, value_color: str = "#e2e8f0", size: str = "sm", bold: bool = False) -> dict:
    return {
        "type": "box", "layout": "horizontal", "margin": "xs",
        "contents": [
            {"type": "text", "text": label, "size": "xs", "color": "#94a3b8", "flex": 3},
            {"type": "text", "text": value, "size": size, "color": value_color,
             "weight": "bold" if bold else "regular", "flex": 5, "wrap": True},
        ]
    }

# ── Webhook ───────────────────────────────────────────────────────────────────
@app.post("/webhook")
async def webhook(request: Request):
    if not _LINE_SDK_OK or not handler:
        raise HTTPException(status_code=503, detail="LINE SDK not configured")
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        log.error(f"handler error: {e}")
    return JSONResponse(content={"status": "ok"})

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "db": os.path.exists(DB_PATH),
        "parquet": os.path.exists(PARQUET_PATH),
        "line_configured": bool(CHANNEL_ACCESS_TOKEN and CHANNEL_SECRET),
        "ts": datetime.now().isoformat(),
    }

# ── Event Handler ─────────────────────────────────────────────────────────────
if _LINE_SDK_OK and handler:
    @handler.add(MessageEvent, message=TextMessageContent)
    def on_message(event: MessageEvent):
        text = event.message.text.strip()
        if not is_plate_query(text):
            return
        plate = normalize_plate(text) or text.upper()
        log.info(f"Plate lookup: {plate}")
        try:
            data    = query_plate(plate)
            flex_j  = build_flex(data)
            with ApiClient(line_cfg) as ac:
                MessagingApi(ac).reply_message(ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[FlexMessage(
                        alt_text=f"ผลค้นหาทะเบียน {plate}",
                        contents=FlexContainer.from_dict(flex_j),
                    )]
                ))
        except Exception as e:
            log.error(f"reply error: {e}")
            try:
                with ApiClient(line_cfg) as ac:
                    MessagingApi(ac).reply_message(ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"❌ ค้นหา {plate} ไม่สำเร็จ")]
                    ))
            except Exception:
                pass

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("LINE_BOT_PORT", 8080))
    log.info(f"LINE Bot starting on port {port}")
    uvicorn.run("line_bot:app", host="0.0.0.0", port=port, workers=1)
