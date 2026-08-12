import psycopg2
con = psycopg2.connect(host='161.118.215.149', port=5432, dbname='itrap_db',
                       user='itrap_admin', password='Hwpd@iTrap2026!Secure', connect_timeout=10)
cur = con.cursor()

print("=== cloud_daily_reports ===")
cur.execute("SELECT report_date, uploaded_by, record_count, created_at FROM cloud_daily_reports ORDER BY report_date DESC LIMIT 5")
rows = cur.fetchall()
if rows:
    for r in rows: print(r)
else:
    print("ไม่มีข้อมูลใน cloud_daily_reports")

print()
print("=== cloud_realtime ===")
cur.execute("SELECT session_date, upload_count, record_count, uploaded_by, updated_at FROM cloud_realtime ORDER BY session_date DESC LIMIT 5")
rows = cur.fetchall()
if rows:
    for r in rows: print(r)
else:
    print("ไม่มีข้อมูลใน cloud_realtime")

con.close()
