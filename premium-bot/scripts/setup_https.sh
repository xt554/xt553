#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

domain="$(grep '^DOMAIN=' .env | cut -d= -f2-)"
email="$(grep '^LETSENCRYPT_EMAIL=' .env | cut -d= -f2-)"
if [[ -z "$domain" || "$domain" == "localhost" || "$domain" == "example.com" ]]; then
  echo "请先在 .env 中设置真实 DOMAIN，并确保 DNS 已指向本机。"
  exit 1
fi
if [[ -z "$email" ]]; then
  echo "请先在 .env 中设置 LETSENCRYPT_EMAIL。"
  exit 1
fi

mkdir -p nginx/certs
docker compose up -d gateway
docker compose --profile https run --rm certbot certonly \
  --webroot --webroot-path /var/www/certbot \
  --domain "$domain" --email "$email" --agree-tos --no-eff-email

sed "s/__DOMAIN__/${domain}/g" nginx/conf.d/ssl.conf.example > nginx/conf.d/ssl.conf
docker compose exec gateway nginx -t
docker compose exec gateway nginx -s reload
echo "HTTPS 已启用：https://${domain}"

