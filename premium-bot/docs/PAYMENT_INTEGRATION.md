# USDT 支付集成

## 支持网络

| 网络 | 数据源 | 默认合约 | 默认精度 |
| --- | --- | --- | --- |
| TRC20 | TronGrid v1 | `TXLAQ...eqcdj` | 6 |
| BEP20 | EVM JSON-RPC `eth_getLogs` | BSC USDT | 18（钱包可改） |
| ERC20 | EVM JSON-RPC `eth_getLogs` | Ethereum USDT | 6 |

钱包记录中的 `token_contract`、`token_decimals`、`min_confirmations` 优先于默认值。添加钱包时务必从链上浏览器和 Token 官方资料核验。

## 扫描流程

1. Celery Beat 每 15 秒触发 `scan_payments`。
2. EVM 扫描器读取最新区块并查询 USDT `Transfer` 日志；为覆盖短重组，会回扫 20 个区块。
3. Tron 扫描器通过 TronGrid 按时间读取已确认 TRC20 交易，并回扫 5 分钟。
4. 交易按唯一键幂等入库。
5. 达到钱包确认数后，先匹配钱包充值单，再匹配 Premium 订单。
6. 充值单匹配成功后原子写入用户钱包；订单匹配成功后变为 `PAID`
   并投递发放任务。

首次启用 EVM 钱包只回扫最近 100 个区块，避免意外扫描整条链。

## 第三方监听 Webhook

也可让自建索引器调用：

```http
POST /api/v1/webhooks/payments
Content-Type: application/json
X-Payment-Signature: HMAC_SHA256(raw_body, PAYMENT_WEBHOOK_SECRET)
```

```json
{
  "network": "TRC20",
  "tx_hash": "transaction-hash",
  "to_address": "T...",
  "from_address": "T...",
  "amount": "29.0371",
  "confirmations": 20,
  "log_index": 0,
  "block_number": 12345678,
  "token_contract": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj"
}
```

签名基于原始请求字节，使用十六进制小写摘要。

## 异常付款

- 少付/多付、错链、未知地址、超过匹配窗口：保留为 `UNMATCHED`，不自动发放。
- 确认数不足：保留为 `DETECTED`，后续回扫会更新。
- 超时后 24 小时内足额到账：从 `TIMEOUT` 转为 `PAID`。
- 钱包充值单超时后 24 小时内足额到账：仍可自动确认并入账。
- 超过 24 小时：人工核对 `payment_transactions` 后处理。

## 退款

工程不保存私钥。管理员退款会调用 `REFUND_PROVIDER_URL` 的独立签名/托管服务：

```json
{
  "reference": "refund-uuid",
  "network": "TRC20",
  "address": "destination",
  "amount": "29.0371",
  "currency": "USDT"
}
```

返回 `reference` 和 `tx_hash`。正式使用前必须加入地址校验、限额、双人审批和热钱包余额控制。

余额支付订单不调用链上退款服务。最终发放失败时，系统通过
`ORDER_REFUND` 账本流水自动把扣款退回用户钱包。
