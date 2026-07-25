# Premium Bot

一个可部署的 Telegram Premium 商店工程：Telegram Bot 负责下单，FastAPI 提供业务接口，MySQL 保存订单，Redis/Celery 处理超时、链上监听、发放和回调，Vue 3 + Element Plus 提供管理后台。

> 默认 `PREMIUM_PROVIDER=mock`，用于完整测试订单链路，不会真实发放 Premium。生产上线前必须接入合法、稳定的发放渠道，并遵守 Telegram、支付服务商及当地法律要求。

## 已包含

- aiogram 3.x Bot：套餐选择、用户名输入、钱包充值、余额支付、订单查询
- FastAPI：JWT 登录、内部 Bot API、管理 API、签名 Webhook
- SQLAlchemy 2 + Alembic + MySQL 8
- Redis：Bot FSM、Celery Broker/Result
- 订单状态机：`WAIT_PAY → PAID → PROCESSING → SUCCESS/FAILED`，含 `TIMEOUT`
- Celery：订单超时、到账扫描、Premium 发放、回调重试、退款任务
- USDT：TRC20（TronGrid）、BEP20/ERC20（EVM JSON-RPC）
- 用户 USDT 钱包：链上充值、自动入账、余额支付、失败自动退款、幂等账本
- Vue 3 + Element Plus：用户、订单、套餐、用户钱包、充值单、收款钱包、日志、统计、参数配置
- Docker Compose、Nginx、HTTPS 脚本、Ubuntu 22.04 安装脚本
- JSON 生产日志、请求 ID、审计日志、HMAC 回调签名

## 目录

```text
premium-bot/
├── api/                 # FastAPI 与管理/内部/Webhook API
├── bot/                 # aiogram 机器人
├── worker/              # Celery 与链上扫描器
├── database/            # SQLAlchemy 模型、种子、Alembic
├── services/            # 订单、支付、发放、退款、回调
├── core/                # 配置、安全、日志、中间件
├── admin/               # Vue 3 + Element Plus
├── docker/              # Python 镜像
├── nginx/               # 网关与 TLS 配置
├── docs/                # 架构、部署与集成文档
├── scripts/             # 部署/HTTPS/Ubuntu 脚本
├── tests/               # 单元测试
└── docker-compose.yml
```

## 快速启动

1. 编辑 `.env`，至少填写 Telegram Token 和一个收款地址：

   ```dotenv
   TELEGRAM_BOT_TOKEN=123456:telegram-token
   TRC20_RECEIVE_ADDRESS=T...
   ```

2. 启动完整服务：

   ```bash
   docker compose --profile telegram up -d --build
   ```

3. 打开：

   - 管理后台：<http://localhost>
   - OpenAPI：<http://localhost/docs>
   - 默认开发账号：`admin / ChangeMe_123!`

生产环境请使用：

```bash
./scripts/deploy.sh your-domain.example
```

脚本会生成数据库密码、JWT Secret、内部 Token 和管理员密码。Ubuntu 22.04 尚未安装 Docker 时，先运行 `sudo ./scripts/install_ubuntu.sh`。

## 关键配置

| 配置 | 说明 |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | BotFather 提供的 Token |
| `*_RECEIVE_ADDRESS` | 各网络 USDT 收款地址 |
| `*_RPC_URL` / `TRONGRID_*` | 链上扫描数据源 |
| `PREMIUM_PROVIDER` | `mock` 或 `webhook` |
| `ALLOW_MOCK_PREMIUM_IN_PRODUCTION` | 是否明确允许生产环境使用 Mock（默认否） |
| `PREMIUM_PROVIDER_URL` | 实际发放渠道 API 根地址 |
| `PAYMENT_UNIQUE_AMOUNT` | 单收款地址时用尾数区分订单 |
| `ORDER_EXPIRE_MINUTES` | 待支付订单有效期 |
| `DEPOSIT_EXPIRE_MINUTES` | 钱包充值单有效期 |
| `WALLET_MIN_DEPOSIT` / `WALLET_MAX_DEPOSIT` | 单笔钱包充值限额 |
| `INTERNAL_API_TOKEN` | Bot 调用内部 API 的凭证 |

所有敏感值应通过环境变量注入。工程不保存钱包私钥；可选退款通过外部签名服务执行。

## 本地开发

后端：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
docker compose up -d mysql redis
export MYSQL_HOST=127.0.0.1
export REDIS_URL=redis://127.0.0.1:6379/0
alembic upgrade head
python -m database.seed
ruff check .
pytest
uvicorn api.main:app --reload
```

前端：

```bash
cd admin
npm install
npm run dev
```

详细说明：

- [架构](docs/ARCHITECTURE.md)
- [部署](docs/DEPLOYMENT.md)
- [USDT 支付](docs/PAYMENT_INTEGRATION.md)
- [用户钱包](docs/USER_WALLET.md)
- [Premium 渠道](docs/PREMIUM_PROVIDER.md)
- [API 与回调](docs/API.md)
- [安全清单](docs/SECURITY.md)

## 生产上线前

- 把 `APP_ENV` 设为 `production`；应用会拒绝明显的默认弱密钥。
- 使用专用收款地址，不要在应用或 `.env` 中保存助记词/私钥。
- 先在测试钱包上验证确认数、Token 合约、金额精度和重组处理。
- 将 Premium Provider 从 `mock` 切换为 `webhook` 并做幂等测试。
- 配置域名、HTTPS、数据库备份、告警和日志留存。
- 完成退款、错链、少付、多付、超时到账的人工处理流程。
- 每日核对链上收款、充值单、钱包账本和用户余额负债总额。

## License

MIT


## Stage 4.1 safety behavior

With `PREMIUM_PROVIDER=mock`, paid orders no longer become successful automatically. They stop at `WAIT_FRAGMENT` until a real fulfillment provider verifies delivery. See `docs/STAGE4_1.md`.


## Fragment Runner Stage 4.3

Production runner observability, persistent browser sessions, account rotation, diagnostics, health reporting, and retry backoff are documented in `docs/STAGE4_3.md`.
