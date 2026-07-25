#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose 未安装。Ubuntu 22.04 可先运行：sudo ./scripts/install_ubuntu.sh"
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

replace_env() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

current_env="$(grep '^APP_ENV=' .env | cut -d= -f2- || true)"
generated_admin_password=""
if [[ "$current_env" != "production" ]] || grep -q "CHANGE_ME" .env; then
  generated_admin_password="$(openssl rand -hex 12)"
  replace_env APP_ENV production
  replace_env DEBUG false
  replace_env MYSQL_PASSWORD "$(openssl rand -hex 18)"
  replace_env MYSQL_ROOT_PASSWORD "$(openssl rand -hex 18)"
  replace_env JWT_SECRET "$(openssl rand -hex 48)"
  replace_env INTERNAL_API_TOKEN "$(openssl rand -hex 32)"
  replace_env PAYMENT_WEBHOOK_SECRET "$(openssl rand -hex 32)"
  replace_env ORDER_CALLBACK_SECRET "$(openssl rand -hex 32)"
  replace_env ADMIN_PASSWORD "$generated_admin_password"
fi

if [[ -n "${1:-}" ]]; then
  replace_env DOMAIN "$1"
  replace_env CORS_ORIGINS "https://$1"
fi

premium_provider="$(grep '^PREMIUM_PROVIDER=' .env | cut -d= -f2- || true)"
allow_mock="$(grep '^ALLOW_MOCK_PREMIUM_IN_PRODUCTION=' .env | cut -d= -f2- || true)"
if [[ "$premium_provider" == "mock" && "$allow_mock" != "true" ]]; then
  echo "生产环境尚未配置真实 Premium Provider。"
  echo "请配置 PREMIUM_PROVIDER=webhook、URL 和 Token；仅测试时可明确设置 ALLOW_MOCK_PREMIUM_IN_PRODUCTION=true。"
  exit 1
fi

telegram_token="$(grep '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2- || true)"
profiles=()
if [[ -n "$telegram_token" ]]; then
  profiles+=(--profile telegram)
fi

docker compose "${profiles[@]}" up -d --build
if [[ -n "$generated_admin_password" ]]; then
  docker compose run --rm api python -m database.admin_cli
fi
docker compose ps

echo
echo "部署完成。后台地址：http://$(grep '^DOMAIN=' .env | cut -d= -f2-)"
echo "管理员用户名：$(grep '^ADMIN_USERNAME=' .env | cut -d= -f2-)"
if [[ -n "$generated_admin_password" ]]; then
  echo "本次生成的管理员密码：$generated_admin_password"
  echo "请立即安全保存并在首次登录后更换。"
fi
echo "配置 HTTPS：sudo ./scripts/setup_https.sh"
