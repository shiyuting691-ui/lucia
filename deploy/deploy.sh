#!/usr/bin/env bash
# ─────────────────────────────────────────
# 极致教育增长作战系统 · 服务器一键部署脚本
# 用法：bash deploy/deploy.sh <GITHUB_REPO_URL>
# 示例：bash deploy/deploy.sh https://github.com/yourname/jizhi-growth-system.git
# ─────────────────────────────────────────
set -e

APP_DIR="/opt/jizhi-growth-system"
REPO_URL="$1"

if [ -z "$REPO_URL" ]; then
  echo "用法: bash deploy/deploy.sh <GITHUB_REPO_URL>"
  exit 1
fi

echo "========================================"
echo " 极致教育增长作战系统 · 部署开始"
echo "========================================"

echo "[1/8] 安装系统依赖..."
sudo apt update -y
sudo apt install -y python3.11 python3.11-venv python3-pip git nginx curl

echo "[2/8] 创建应用目录..."
sudo mkdir -p $APP_DIR
sudo chown -R $USER:$USER $APP_DIR

echo "[3/8] 拉取代码..."
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  cd "$APP_DIR"
  git pull
fi

cd "$APP_DIR"

echo "[4/8] 创建虚拟环境..."
python3.11 -m venv .venv
source .venv/bin/activate

echo "[5/8] 安装 Python 依赖..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[6/8] 创建必要目录..."
mkdir -p data logs outputs backups
mkdir -p knowledge_base/00_公司事实源
mkdir -p knowledge_base/01_部门职责
mkdir -p knowledge_base/02_产品体系
mkdir -p knowledge_base/03_销售话术
mkdir -p knowledge_base/04_客户异议
mkdir -p knowledge_base/05_风控表达
mkdir -p knowledge_base/06_学管交付
mkdir -p knowledge_base/07_老师储备
mkdir -p knowledge_base/08_订单咨询数据说明
mkdir -p knowledge_base/09_优秀内容样例
mkdir -p knowledge_base/10_禁用表达
mkdir -p knowledge_base/11_组织命名规则

echo "[7/8] 检查 .env 文件..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "⚠️  .env 已从模板创建，请立即编辑填写真实值："
  echo "    nano $APP_DIR/.env"
  echo ""
fi

echo "[8/8] 初始化数据库..."
source .venv/bin/activate
python main.py init || true

echo ""
echo "========================================"
echo " 部署文件准备完毕！"
echo "========================================"
echo ""
echo "接下来请手动执行："
echo ""
echo "  1. 编辑 .env 填写 API Key："
echo "     nano $APP_DIR/.env"
echo ""
echo "  2. 安装 systemd 服务："
echo "     sudo cp $APP_DIR/deploy/jizhi-growth.service /etc/systemd/system/"
echo "     sudo systemctl daemon-reload"
echo "     sudo systemctl enable jizhi-growth"
echo "     sudo systemctl start jizhi-growth"
echo ""
echo "  3. 配置 Nginx："
echo "     sudo cp $APP_DIR/deploy/jizhi-growth.nginx.conf /etc/nginx/sites-available/jizhi-growth"
echo "     sudo ln -sf /etc/nginx/sites-available/jizhi-growth /etc/nginx/sites-enabled/jizhi-growth"
echo "     sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "  4. 配置 crontab："
echo "     crontab -e  # 参考 deploy/crontab.example"
echo ""
echo "  5. 健康检查："
echo "     cd $APP_DIR && source .venv/bin/activate && python main.py health-check"
echo ""
