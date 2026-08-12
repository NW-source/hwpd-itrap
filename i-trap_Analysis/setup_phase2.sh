#!/bin/bash
set -e
echo "=== HWPD i-Trap Analysis Setup Phase 2 ==="
sudo chmod -R 755 /home/ubuntu/itrap_agent
sudo chown -R ubuntu:ubuntu /home/ubuntu/itrap_agent
PG_VER=$(ls /etc/postgresql/ | head -n 1)
echo "PostgreSQL version: $PG_VER"
sudo -u postgres psql -f /home/ubuntu/itrap_agent/setup_itrap_pg.sql
echo "Step 5: PostgreSQL schema done"
sudo sed -i "s/#listen_addresses = .localhost./listen_addresses = '*'/" /etc/postgresql/$PG_VER/main/postgresql.conf
if ! sudo grep -q "itrap_admin.*0.0.0.0" /etc/postgresql/$PG_VER/main/pg_hba.conf; then
    echo "host    itrap_db    itrap_admin    0.0.0.0/0    scram-sha-256" | sudo tee -a /etc/postgresql/$PG_VER/main/pg_hba.conf
fi
sudo systemctl restart postgresql
echo "Step 6: PostgreSQL remote access configured"
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8501 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT 2>/dev/null || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 5432 -j ACCEPT 2>/dev/null || true
sudo netfilter-persistent save 2>/dev/null || true
echo "Step 7: Firewall ports opened"
sudo tee /etc/systemd/system/itrap-analysis.service > /dev/null << EOF
[Unit]
Description=HWPD i-Trap Analysis App
After=network.target postgresql.service
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/itrap_agent
ExecStart=/home/ubuntu/itrap_agent/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true
Restart=always
RestartSec=5
Environment=ITRAP_HOST=129.150.56.185
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/itrap-linebot.service > /dev/null << EOF
[Unit]
Description=HWPD i-Trap LINE Bot
After=network.target postgresql.service
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/itrap_agent
ExecStart=/home/ubuntu/itrap_agent/venv/bin/uvicorn line_bot:app --host 0.0.0.0 --port 8080 --workers 1
Restart=always
RestartSec=5
Environment=ITRAP_DATA_DIR=/home/ubuntu/itrap_agent
Environment=ITRAP_HOST=129.150.56.185
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable itrap-analysis itrap-linebot
sudo systemctl start itrap-analysis itrap-linebot
sleep 3
echo "=== Service Status ==="
sudo systemctl is-active itrap-analysis && echo "itrap-analysis: RUNNING" || echo "itrap-analysis: FAILED"
sudo systemctl is-active itrap-linebot && echo "itrap-linebot: RUNNING" || echo "itrap-linebot: FAILED"
echo "Web: http://129.150.56.185:8501"
echo "LINE Bot: http://129.150.56.185:8080"
echo "=== COMPLETE ==="