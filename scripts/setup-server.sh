#!/usr/bin/env bash
# LIFEE 阿里云轻量（Ubuntu 24.04）一次性部署脚本
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/Ruzhenzrose/LIFEE/main/scripts/setup-server.sh -o setup.sh
#   bash setup.sh
# 或：
#   git clone https://github.com/Ruzhenzrose/LIFEE.git /opt/lifee && cd /opt/lifee && bash scripts/setup-server.sh

set -euo pipefail

APP_DIR="/opt/lifee"
REPO_URL="https://github.com/Ruzhenzrose/LIFEE.git"
SERVICE_NAME="lifee"
PY="python3.12"

echo "==> 1/7 更新系统 + 装依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    $PY ${PY}-venv ${PY}-dev \
    git curl build-essential \
    nginx certbot python3-certbot-nginx \
    ufw sqlite3

echo "==> 2/7 防火墙（UFW 本机层；阿里云安全组另外配）"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> 3/7 拉代码到 $APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
    mkdir -p "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
else
    cd "$APP_DIR"
    git pull --ff-only || echo "(git pull 失败，手动处理)"
fi
cd "$APP_DIR"

echo "==> 4/7 Python venv + 装 requirements"
if [ ! -d venv ]; then
    $PY -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

echo "==> 5/7 systemd 服务（还没启动，等 .env 放好再 enable）"
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=LIFEE FastAPI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/venv/bin/uvicorn lifee.api:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/lifee.log
StandardError=append:/var/log/lifee.log

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload

echo "==> 6/7 Nginx 反代（先配 HTTP，等 DNS 解析生效后再用 certbot 加 HTTPS）"
cat > /etc/nginx/sites-available/${SERVICE_NAME} <<'EOF'
server {
    listen 80 default_server;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        # FastAPI 流式响应用的长超时
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_buffering off;
    }
}
EOF
ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/${SERVICE_NAME}
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> 7/7 完成"
cat <<'EOF'

─────────────────────────────────────────────
下一步（需要你手动做）：
─────────────────────────────────────────────

1. 把 .env 文件上传到 /opt/lifee/.env
   本地运行：
   scp .env root@47.83.184.82:/opt/lifee/.env

2. 启动 LIFEE 服务：
   systemctl enable --now lifee
   systemctl status lifee       # 看是否 running
   tail -f /var/log/lifee.log   # 看日志

3. 测试（浏览器访问 http://47.83.184.82/ ）
   或 curl http://127.0.0.1:8000/healthz

4. 绑定域名（等你买好 lifee.com）：
   - 去 DNS 服务商加 A 记录：www.lifee.com → 47.83.184.82
   - 等 5-10 分钟解析生效，dig www.lifee.com 能看到 IP
   - 改 nginx server_name，然后跑 certbot 申请 HTTPS：
     sed -i 's/server_name _;/server_name www.lifee.com lifee.com;/' \
         /etc/nginx/sites-available/lifee
     nginx -t && systemctl reload nginx
     certbot --nginx -d www.lifee.com -d lifee.com

EOF
