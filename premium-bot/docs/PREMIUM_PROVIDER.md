# Premium Provider 接入

核心接口位于 `services/premium.py`：

```python
class PremiumService:
    async def create_order(self, username, months): ...

    async def purchase(self, order_id): ...

    async def query(self, order_id): ...
```

## Mock

```dotenv
PREMIUM_PROVIDER=mock
```

Mock 会立即返回成功，只用于开发、演示和自动化测试。

## Webhook/HTTP Provider

```dotenv
PREMIUM_PROVIDER=webhook
PREMIUM_PROVIDER_URL=https://provider.example/api
PREMIUM_PROVIDER_TOKEN=secret-token
```

约定：

### 创建渠道订单

```http
POST /orders
Authorization: Bearer <token>

{"username":"@username","months":3}
```

### 执行购买

```http
POST /orders/{provider_order_id}/purchase
```

### 查询

```http
GET /orders/{provider_order_id}
```

统一响应：

```json
{
  "order_id": "provider-order-id",
  "status": "SUCCESS",
  "message": "delivered"
}
```

状态支持 `CREATED`、`PROCESSING`、`SUCCESS`、`FAILED`。处理中会由 Celery 指数退避重试；最终状态写入订单状态历史。

异步渠道可回调 `/api/v1/webhooks/premium`。请求原始 Body 使用 `PREMIUM_PROVIDER_TOKEN` 做 HMAC-SHA256，并在 `X-Premium-Signature` 中传递。

## 新适配器

继承 `PremiumService`，实现三个方法，并在 `get_premium_service()` 注册。Provider 必须：

- 用本系统的 `premium_reference` 做幂等键；
- 重复 purchase 不重复扣款或赠送；
- query 返回稳定终态；
- 不在日志中输出渠道 Token；
- 明确区分“目标用户名无效”和“临时系统错误”。

