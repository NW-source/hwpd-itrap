#!/bin/bash
set -e
echo "========================================================="
echo "   HWPD i-Trap Master Setup for Oracle Cloud (Ubuntu)    "
echo "========================================================="

# 1) System update & packages
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-venv postgresql postgresql-contrib git curl iptables-persistent

# 2) Repository setup
TARGET_DIR="/home/ubuntu/itrap_agent"
if [ ! -d "$TARGET_DIR" ]; then
    git clone https://github.com/NW-source/hwpd-itrap.git "$TARGET_DIR"
else
    cd "$TARGET_DIR" && git pull origin main
fi
cd "$TARGET_DIR"

# 3) Python Virtual Environment & Requirements
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4) Setup PostgreSQL Database
sudo -u postgres psql -f "$TARGET_DIR/setup_itrap_pg.sql" || true

# Configure PostgreSQL remote listening
PG_VER=$(ls /etc/postgresql/ | head -n 1)
if [ -n "$PG_VER" ]; then
    sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "/etc/postgresql/$PG_VER/main/postgresql.conf" || true
    if ! sudo grep -q "itrap_admin.*0.0.0.0" "/etc/postgresql/$PG_VER/main/pg_hba.conf"; then
        echo "host    itrap_db    itrap_admin    0.0.0.0/0    scram-sha-256" | sudo tee -a "/etc/postgresql/$PG_VER/main/pg_hba.conf"
    fi
    sudo systemctl restart postgresql
fi

# 5) Setup Systemd Service 1: Main Streamlit App (Port 8501)
sudo cat << 'EOF' | sudo tee /etc/systemd/system/itrap.service
[Unit]
Description=HWPD i-Trap Main Analysis App
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/itrap_agent
ExecStart=/home/ubuntu/itrap_agent/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 6) Setup Systemd Service 2: LINE Bot Webhook Server (Port 8080)
sudo cat << 'EOF' | sudo tee /etc/systemd/system/itrap-linebot.service
[Unit]
Description=HWPD i-Trap LINE Bot Server
After=network.target postgresql.service

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/itrap_agent
ExecStart=/home/ubuntu/itrap_agent/venv/bin/uvicorn line_bot:app --host 0.0.0.0 --port 8080 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 7) Open Linux Firewall ports (8501, 8080, 5432)
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8501 -j ACCEPT || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8080 -j ACCEPT || true
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 5432 -j ACCEPT || true
sudo netfilter-persistent save || true

# 8) Reload systemd and start all services
sudo systemctl daemon-reload
sudo systemctl enable itrap itrap-linebot
sudo systemctl restart itrap itrap-linebot

echo "========================================================="
echo "   SETUP COMPLETE!                                       "
echo "   Main i-Trap App : http://161.118.215.149:8501        "
echo "   LINE Bot Server : http://161.118.215.149:8080        "
echo "   PostgreSQL DB   : Port 5432 (itrap_db / itrap_admin) "
echo "========================================================="
