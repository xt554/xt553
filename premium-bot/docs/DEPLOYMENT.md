# 部署指南

## Ubuntu 22.04 一键部署

```bash
unzip premium-bot.zip
cd premium-bot
sudo ./scripts/install_ubuntu.sh   # 已有 Docker 时跳过
cp .env.example .env
nano .env
./scripts/deploy.sh shop.example.com
```

必须先配置：

- `TELEGRAM_BOT_TOKEN`
- 至少一个 `TRC20_RECEIVE_ADDRESS` / `BEP20_RECEIVE_ADDRESS`
- 对应的 RPC 或 TronGrid API
- 合法可用的 Premium Provider（正式环境）

`deploy.sh` 会把开发环境切换为生产环境并生成强随机密码。请保存脚本输出的管理员密码。

## HTTPS

先将域名 A/AAAA 记录指向服务器，开放 80/443，并在 `.env` 设置：

```dotenv
DOMAIN=shop.example.com
CORS_ORIGINS=https://shop.example.com
LETSENCRYPT_EMAIL=ops@example.com
```

然后：

```bash
sudo ./scripts/setup_https.sh
```

证书保存在 `nginx/certs/`，不进入 Git。续期可加入 root cron：

```cron
15 3 * * * cd /opt/premium-bot && docker compose --profile https run --rm certbot renew --webroot -w /var/www/certbot --quiet && docker compose exec gateway nginx -s reload
```

## 常用命令

```bash
docker compose ps
docker compose logs -f --tail=200 api worker bot
docker compose run --rm migrate
docker compose restart worker beat
docker compose exec mysql mysqldump -u root -p premium_bot > backup.sql
```

Bot 使用 Compose profile。配置 Token 后：

```bash
docker compose --profile telegram up -d bot
```

## 扩容

- API 可使用 `docker compose up -d --scale api=3`，同时移除固定容器名（工程未设置）。
- Worker 可按队列独立扩容：`payments`、`fulfillment`、`default`。
- 多实例 Beat 只能运行一个，否则会重复调度；任务自身仍以数据库幂等保护。
- 更大规模建议使用托管 MySQL/Redis、负载均衡器和专用 Celery 监控。

## 数据库迁移

容器启动时 `migrate` 服务先执行 `alembic upgrade head`。发布前可先检查：

```bash
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic history
```

`20260724_0002` 会创建用户钱包、充值单和账本，并为已有用户初始化
零余额钱包。生产升级前先备份；订单、支付和钱包表不建议自动降级删除。

上线后请将管理后台概览的“用户钱包余额”作为平台 USDT 负债，与链上
收款地址余额、待处理订单及已提现资金每日对账。
