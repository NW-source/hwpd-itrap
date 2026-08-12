#!/bin/bash
# HWPD i-Trap Nightly Cleanup ? ????? 3 ??????
LOG="/var/log/itrap-cleanup.log"
TS=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$TS] === Nightly Cleanup Start ===" >> $LOG

# 1) Restart Streamlit (???? RAM cache)
systemctl restart itrap-analysis
echo "[$TS] itrap-analysis restarted" >> $LOG

# 2) Restart LINE Bot
systemctl restart itrap-linebot
echo "[$TS] itrap-linebot restarted" >> $LOG

# 3) ???? journal logs ???????? 7 ???
journalctl --vacuum-time=7d >> $LOG 2>&1
echo "[$TS] journal vacuumed" >> $LOG

# 4) PostgreSQL VACUUM
PGPASSWORD='Hwpd@iTrap2026!Secure' psql -h 127.0.0.1 -U itrap_admin -d itrap_db \
  -c "VACUUM ANALYZE watchlist; VACUUM ANALYZE line_config;" >> $LOG 2>&1
echo "[$TS] PostgreSQL vacuumed" >> $LOG

# 5) ???? /tmp ???????? 1 ???
find /tmp -type f -mtime +1 -delete 2>/dev/null
echo "[$TS] /tmp cleaned" >> $LOG

# 6) ???? RAM ???? cleanup
free -h >> $LOG
echo "[$TS] === Cleanup Done ===" >> $LOG