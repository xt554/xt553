# API 摘要

完整 OpenAPI 在运行后访问 `/docs`。

## 管理认证

```http
POST /api/v1/auth/login
Content-Type: application/json

{"username":"admin","password":"..."}
```

返回 JWT access/refresh token。后台请求使用：

```http
Authorization: Bearer <access_token>
```

## Bot 内部 API

内部接口要求：

```http
X-Internal-Token: <INTERNAL_API_TOKEN>
```

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/v1/internal/users/telegram` | 注册/更新 Telegram 用户 |
| GET | `/api/v1/internal/plans` | 获取启用套餐 |
| GET | `/api/v1/internal/networks` | 获取启用网络 |
| POST | `/api/v1/internal/orders` | 创建订单 |
| GET | `/api/v1/internal/orders/{order_no}` | 查询当前用户订单 |
| GET | `/api/v1/internal/wallet` | 查询当前用户 USDT 钱包 |
| GET | `/api/v1/internal/wallet/ledger` | 查询余额流水 |
| POST | `/api/v1/internal/wallet/deposits` | 创建链上充值单 |
| GET | `/api/v1/internal/wallet/deposits/{deposit_no}` | 查询充值单 |

余额支付创建订单示例：

```json
{
  "telegram_id": 123456,
  "plan_id": "plan-uuid",
  "target_username": "@username",
  "network": null,
  "payment_method": "WALLET_BALANCE"
}
```

## 管理 API

| 资源 | 路径 |
| --- | --- |
| 概览 | `/api/v1/admin/stats` |
| 用户 | `/api/v1/admin/users` |
| 套餐 | `/api/v1/admin/plans` |
| 订单 | `/api/v1/admin/orders` |
| 用户钱包、充值单、账本、调账 | `/api/v1/admin/wallet-accounts` |
| 链上收款钱包 | `/api/v1/admin/wallets` |
| 审计日志 | `/api/v1/admin/logs` |
| 参数 | `/api/v1/admin/settings` |

## 订单状态回调

内部创建订单时可传 HTTPS `callback_url`。状态变化后发送：

```json
{
  "event": "order.updated",
  "order_no": "NO202607240001",
  "status": "SUCCESS",
  "payment_method": "ONCHAIN",
  "network": "TRC20",
  "amount": "29.037100",
  "tx_hash": "...",
  "premium_reference": "...",
  "updated_at": "2026-07-24T00:00:00+00:00"
}
```

请求头 `X-Premium-Signature` 是 `HMAC_SHA256(raw_body, ORDER_CALLBACK_SECRET)`。接收方需防重放并幂等处理。
