#!/bin/bash
# ============================================
# Smart Doc Platform - 一键部署脚本 (Ubuntu/Debian)
# ============================================
# 使用方法:
#   1. 将此脚本和 deploy/ 目录放到服务器上
#   2. chmod +x deploy.sh && sudo ./deploy.sh
#
# 首次部署前请先准备好 backend/.env 文件 (含 DeepSeek API Key 等)
# ============================================

set -e

APP_DIR="/opt/smart-doc-platform"
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_DIR="$APP_DIR/frontend"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---------- 检查 root ----------
if [ "$EUID" -ne 0 ]; then
    log_error "请用 sudo 运行此脚本: sudo ./deploy.sh"
    exit 1
fi

# ---------- 步骤 1: 安装系统依赖 ----------
log_info "步骤 1/6: 安装系统依赖..."

apt-get update -qq

# Nginx
if ! command -v nginx &> /dev/null; then
    log_info "安装 Nginx..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx
fi

# Python 3 虚拟环境
if ! dpkg -l python3-venv &> /dev/null; then
    log_info "安装 Python3 虚拟环境..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip
fi

# Node.js 18+ (Vite 5 需要)
if ! command -v node &> /dev/null || [ "$(node -v | cut -d. -f1 | tr -d 'v')" -lt 18 ]; then
    log_info "安装 Node.js 18..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs
fi

log_info "系统依赖安装完成"

# ---------- 步骤 2: 部署后端 ----------
log_info "步骤 2/6: 部署后端代码..."

mkdir -p "$APP_DIR"

# 复制后端代码
if [ -d "$BACKEND_DIR" ]; then
    log_info "后端目录已存在，仅更新代码 (不覆盖 .env 和 app.db)..."
    rsync -a --exclude='.env' --exclude='app.db' --exclude='venv' --exclude='static/' \
        "$PROJECT_DIR/backend/" "$BACKEND_DIR/"
else
    log_info "首次部署，复制后端代码..."
    rsync -a --exclude='.env' --exclude='app.db' --exclude='venv' \
        "$PROJECT_DIR/backend/" "$BACKEND_DIR/"
fi

# Python 虚拟环境
if [ ! -d "$BACKEND_DIR/venv" ]; then
    log_info "创建 Python 虚拟环境..."
    python3 -m venv "$BACKEND_DIR/venv"
fi

log_info "安装 Python 依赖..."
"$BACKEND_DIR/venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

# .env 文件
if [ ! -f "$BACKEND_DIR/.env" ]; then
    if [ -f "$PROJECT_DIR/backend/.env" ]; then
        cp "$PROJECT_DIR/backend/.env" "$BACKEND_DIR/.env"
        log_info "已复制 .env 配置文件"
    else
        log_warn "未找到 .env 文件！请手动创建 $BACKEND_DIR/.env"
        log_warn "参考内容:"
        log_warn "  KIMI_API_KEY=sk-xxx"
        log_warn "  KIMI_MODEL=moonshot-v1-8k"
        log_warn "  DEFAULT_MODEL_PROVIDER=kimi"
    fi
fi

# 上传目录
mkdir -p "$BACKEND_DIR/static/uploads"
mkdir -p "$BACKEND_DIR/static/knowledge"
mkdir -p "$BACKEND_DIR/static/polished"

chown -R www-data:www-data "$BACKEND_DIR/static"

log_info "后端部署完成"

# ---------- 步骤 3: 构建前端 ----------
log_info "步骤 3/6: 构建前端..."

# 复制前端代码
if [ -d "$FRONTEND_DIR" ]; then
    rsync -a --exclude='node_modules' --exclude='dist' "$PROJECT_DIR/frontend/" "$FRONTEND_DIR/"
else
    rsync -a --exclude='node_modules' "$PROJECT_DIR/frontend/" "$FRONTEND_DIR/"
fi

cd "$FRONTEND_DIR"

log_info "安装前端依赖..."
npm install --silent 2>&1 | tail -1

log_info "构建生产版本..."
npm run build 2>&1 | tail -3

chown -R www-data:www-data "$FRONTEND_DIR/dist"

log_info "前端构建完成 → $FRONTEND_DIR/dist"

# ---------- 步骤 4: 配置 Nginx ----------
log_info "步骤 4/6: 配置 Nginx..."

cp "$PROJECT_DIR/deploy/nginx.conf" /etc/nginx/sites-available/smart-doc-platform

# 启用站点
if [ ! -L /etc/nginx/sites-enabled/smart-doc-platform ]; then
    ln -sf /etc/nginx/sites-available/smart-doc-platform /etc/nginx/sites-enabled/
fi

# 禁用默认站点
if [ -L /etc/nginx/sites-enabled/default ]; then
    rm -f /etc/nginx/sites-enabled/default
fi

# 测试配置
if nginx -t 2>&1; then
    systemctl reload nginx
    log_info "Nginx 配置完成"
else
    log_error "Nginx 配置测试失败，请检查 /etc/nginx/sites-available/smart-doc-platform"
    exit 1
fi

# ---------- 步骤 5: 配置 systemd ----------
log_info "步骤 5/6: 配置 systemd 服务..."

cp "$PROJECT_DIR/deploy/smart-doc-platform.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable smart-doc-platform
systemctl restart smart-doc-platform

log_info "Systemd 服务已配置并启动"

# ---------- 步骤 6: 检查状态 ----------
log_info "步骤 6/6: 检查服务状态..."

sleep 2

echo ""
echo "============================================"
echo "  部署完成！"
echo "============================================"
echo ""

# Nginx 状态
if systemctl is-active --quiet nginx; then
    log_info "Nginx:      运行中 (端口 80)"
else
    log_error "Nginx:      未运行"
fi

# 后端状态
if systemctl is-active --quiet smart-doc-platform; then
    log_info "后端:       运行中 (端口 8000)"
else
    log_warn "后端:       未运行，查看日志: journalctl -u smart-doc-platform -f"
fi

# 检查前端文件
if [ -f "$FRONTEND_DIR/dist/index.html" ]; then
    log_info "前端:       已构建 ($FRONTEND_DIR/dist)"
else
    log_error "前端:       未构建"
fi

# 检查 .env
if [ -f "$BACKEND_DIR/.env" ]; then
    log_info "环境变量:   $BACKEND_DIR/.env"
else
    log_warn "环境变量:   缺失！请创建 $BACKEND_DIR/.env"
fi

echo ""
echo "访问地址: http://<服务器IP>"
echo ""
echo "管理命令:"
echo "  systemctl status smart-doc-platform   # 查看后端状态"
echo "  journalctl -u smart-doc-platform -f   # 查看后端日志"
echo "  systemctl restart smart-doc-platform  # 重启后端"
echo "  systemctl reload nginx                # 重载 Nginx"
echo ""
echo "更新部署 (代码有改动后):"
echo "  ./deploy.sh"
echo "============================================"
