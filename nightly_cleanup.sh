#!/bin/bash
# /home/ubuntu/nightly_cleanup.sh
# Nightly Cleanup Script สำหรับ HWPD i-Trap Oracle Cloud
# รันทุกคืนตี 2 โดย cron

LOG=/home/ubuntu/nightly_cleanup.log
TS=$(date '+%Y-%m-%d %H:%M:%S')

echo "" >> $LOG
echo "========================================" >> $LOG
echo "[$TS] === NIGHTLY CLEANUP START ===" >> $LOG
echo "========================================" >> $LOG

# RAM ก่อน cleanup
RAM_BEFORE=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo)
echo "[$TS] RAM available before: ${RAM_BEFORE}MB" >> $LOG

# ─── 1. Restart itrap.service ────────────────────────────────
echo "[$TS] [1/5] Restarting itrap.service..." >> $LOG
sudo systemctl restart itrap.service
sleep 3
ITRAP_STATUS=$(systemctl is-active itrap.service)
echo "[$TS]       itrap.service: $ITRAP_STATUS" >> $LOG

# ─── 2. Restart itrap-linebot (ถ้ามี) ───────────────────────
echo "[$TS] [2/5] Checking itrap-linebot..." >> $LOG
if systemctl is-active --quiet itrap-linebot.service 2>/dev/null; then
    sudo systemctl restart itrap-linebot.service
    sleep 2
    BOT_STATUS=$(systemctl is-active itrap-linebot.service)
    echo "[$TS]       itrap-linebot: $BOT_STATUS" >> $LOG
else
    echo "[$TS]       itrap-linebot: not installed (skip)" >> $LOG
fi

# ─── 3. Clear systemd journal logs เก่า > 7 วัน ────────────
echo "[$TS] [3/5] Clearing journal logs older than 7 days..." >> $LOG
BEFORE=$(sudo journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+ [MGK]?B' | head -1)
sudo journalctl --vacuum-time=7d >> $LOG 2>&1
AFTER=$(sudo journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+ [MGK]?B' | head -1)
echo "[$TS]       Journal: $BEFORE -> $AFTER" >> $LOG

# ─── 4. PostgreSQL VACUUM ────────────────────────────────────
echo "[$TS] [4/5] Running PostgreSQL VACUUM..." >> $LOG
PGPASSWORD='Hwpd@iTrap2026!Secure' psql -h 127.0.0.1 -U itrap_admin -d itrap_db \
    -c "VACUUM ANALYZE;" >> $LOG 2>&1
echo "[$TS]       VACUUM done" >> $LOG

# ─── 5. Clear /tmp files เก่า > 1 วัน ───────────────────────
echo "[$TS] [5/5] Clearing /tmp files older than 1 day..." >> $LOG
TMP_BEFORE=$(du -sh /tmp 2>/dev/null | cut -f1)
find /tmp -type f -mtime +1 -delete 2>/dev/null
find /tmp -type d -empty -not -name tmp -delete 2>/dev/null
TMP_AFTER=$(du -sh /tmp 2>/dev/null | cut -f1)
echo "[$TS]       /tmp: $TMP_BEFORE -> $TMP_AFTER" >> $LOG

# RAM หลัง cleanup
sleep 5
RAM_AFTER=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo)
echo "[$TS] RAM available after: ${RAM_AFTER}MB (freed: $((RAM_AFTER - RAM_BEFORE))MB)" >> $LOG
echo "[$TS] === NIGHTLY CLEANUP COMPLETE ===" >> $LOG

# เก็บ log ไว้ 30 วัน (1500 บรรทัด)
tail -n 1500 $LOG > /tmp/cleanup_tmp && mv /tmp/cleanup_tmp $LOG
