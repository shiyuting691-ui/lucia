# 极致教育增长作战系统 · 部署手册

## 安全提醒（必读）

> ⚠️ 以下文件**绝对不允许**提交到 GitHub：
> - `.env`（含 API Key）
> - `marketing.db`（数据库）
> - `data/orders_2025*.csv` / `data/leads_2025*.csv`（真实业务数据）
> - `knowledge_base/` 下的所有业务资料（产品说明、话术、风控规则等）

---

## 本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/shiyuting691-ui/lucia.git
cd lucia

# 2. 创建虚拟环境
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
nano .env                        # 填写 ANTHROPIC_API_KEY 和 WECHAT_WORK_WEBHOOK

# 5. 初始化数据库
python main.py init

# 6. 健康检查
python main.py health-check

# 7. 启动 Dashboard
python main.py dashboard
# 或者直接：
streamlit run dashboard.py
```

访问：http://localhost:8501

---

## 数据导入

```bash
# 导入历史订单
python main.py ingest-orders data/orders_sample.csv

# 导入线索数据
python main.py ingest-leads data/leads_sample.csv

# 导入老师储备数据
python main.py ingest-teacher-capacity data/teacher_capacity_sample.csv

# 更新市场信号
python main.py update-market-signals

# 更新订单风险
python main.py update-order-risks
```

---

## 服务器部署（121.43.83.158）

### 第一步：SSH 登录服务器

```bash
ssh root@121.43.83.158
```

### 第二步：克隆代码

```bash
git clone https://github.com/shiyuting691-ui/lucia.git /opt/jizhi-growth-system
cd /opt/jizhi-growth-system
```

### 第三步：一键部署

```bash
bash deploy/deploy.sh https://github.com/shiyuting691-ui/lucia.git
```

脚本会自动完成：安装 Python 3.11、创建虚拟环境、安装依赖、创建目录、初始化数据库。

### 第四步：填写环境变量

```bash
nano /opt/jizhi-growth-system/.env
```

至少填写：
```
ANTHROPIC_API_KEY=sk-ant-...
WECHAT_WORK_WEBHOOK=https://qyapi.weixin.qq.com/...
```

### 第五步：安装 systemd 服务（开机自启）

```bash
sudo cp deploy/jizhi-growth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable jizhi-growth
sudo systemctl start jizhi-growth
sudo systemctl status jizhi-growth
```

### 第六步：配置 Nginx 反向代理

```bash
sudo cp deploy/jizhi-growth.nginx.conf /etc/nginx/sites-available/jizhi-growth
sudo ln -sf /etc/nginx/sites-available/jizhi-growth /etc/nginx/sites-enabled/jizhi-growth
sudo nginx -t
sudo systemctl reload nginx
```

访问：http://121.43.83.158

### 第七步：配置定时任务

```bash
crontab -e
# 粘贴 deploy/crontab.example 的内容
```

---

## 更新部署

```bash
ssh root@121.43.83.158
cd /opt/jizhi-growth-system
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart jizhi-growth
```

---

## 查看日志

```bash
# systemd 服务日志（实时）
journalctl -u jizhi-growth -f

# crontab 任务日志
tail -f /opt/jizhi-growth-system/logs/daily_reminder.log
tail -f /opt/jizhi-growth-system/logs/weekly_promotion.log
```

---

## 健康检查

```bash
cd /opt/jizhi-growth-system
source .venv/bin/activate
python main.py health-check
```

---

## 常见问题

**Q：启动后看不到页面**
检查 Nginx 是否运行：`sudo systemctl status nginx`
检查服务是否启动：`sudo systemctl status jizhi-growth`
检查端口是否开放：`sudo ufw allow 80`

**Q：AI 建议不生成**
检查 `.env` 中 `ANTHROPIC_API_KEY` 是否正确填写。

**Q：企业微信推送失败**
检查 `WECHAT_WORK_WEBHOOK` 是否正确，Webhook URL 是否过期。

**Q：数据库为空**
重新运行 `python main.py init` 和数据导入命令。
