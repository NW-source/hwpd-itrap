#!/bin/bash
THRESHOLD_MB=10240
LOG=/home/ubuntu/itrap_memwatch.log
SERVICE=itrap.service
USED_MB=$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf "%d", (t-a)/1024}' /proc/meminfo)
TOTAL_MB=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
TS=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$TS] RAM: ${USED_MB}MB / ${TOTAL_MB}MB" >> $LOG
if [ "$USED_MB" -ge "$THRESHOLD_MB" ]; then
  echo "[$TS] WARNING: RAM exceeded threshold -- restarting $SERVICE" >> $LOG
  sudo systemctl restart $SERVICE
  sleep 5
  echo "[$TS] Done: $(systemctl is-active $SERVICE)" >> $LOG
fi
tail -n 500 $LOG > /tmp/mw_tmp && mv /tmp/mw_tmp $LOG
