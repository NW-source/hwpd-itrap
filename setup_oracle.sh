#!/bin/bash
set -e
echo "========================================="
echo "   HWPD i-Trap Auto Setup for Oracle     "
echo "========================================="

# Update packages
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-venv git curl iptables-persistent

# Clone repository
if [ ! -d "/home/ubuntu/hwpd-itrap" ]; then
    git clone https://github.com/NW-source/hwpd-itrap.git /home/ubuntu/hwpd-itrap
else
    cd /home/ubuntu/hwpd-itrap && git pull origin main
fi

cd /home/ubuntu/hwpd-itrap

# Setup Python Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Setup Secrets
mkdir -p .streamlit
cat << 'EOF' > .streamlit/secrets.toml
[supabase]
url = "https://tailghdkzctupfadbgjl.supabase.co"
key = "sb_publishable_FTDCiI38xAUn2_8gRAPjWQ_XbI3v9Gy"
EOF

# Setup Systemd Service (Auto-Start 24/7)
sudo cat << 'EOF' | sudo tee /etc/systemd/system/itrap.service
[Unit]
Description=HWPD i-Trap Streamlit Cloud App
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/hwpd-itrap
ExecStart=/home/ubuntu/hwpd-itrap/venv/bin/streamlit run cloud_app.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Open Linux Firewall port 8501 inside Ubuntu
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8501 -j ACCEPT
sudo netfilter-persistent save || true

# Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable itrap
sudo systemctl restart itrap

echo "========================================="
echo "   SETUP COMPLETE!                       "
echo "   App is running on port 8501           "
echo "========================================="
