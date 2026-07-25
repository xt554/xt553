# 钱包购买流程 V2 部署说明

## 本次改动

- 删除购买时的“请选择支付方式”。
- 钱包余额充足：直接显示“立即支付”。
- 钱包余额不足：显示余额、价格和差额，进入钱包充值。
- 充值支持快捷金额：10 / 20 / 50 / 100 / 200 / 500 USDT。
- 支持 5～10000 USDT 自定义充值金额。
- 因购买触发的充值单到账后，点击“刷新到账状态”会自动恢复原套餐和 Telegram 用户名，随后可立即支付。
- 钱包余额是唯一的套餐支付方式。
- 保留充值网络选择与精确金额匹配。

## 覆盖部署

```bash
cd /www/wwwroot
cp -a premium-bot premium-bot-backup-$(date +%Y%m%d-%H%M%S)
unzip premium-bot-wallet-v2.zip
cd premium-bot
docker compose build --no-cache api bot worker beat
docker compose up -d
docker compose ps
docker compose logs --tail=100 bot api worker
```

压缩包不包含 `.env`，覆盖部署不会替换服务器现有密钥和配置。

## 验证流程

1. 选择套餐并输入 Telegram 用户名。
2. 余额充足时确认只出现“立即支付”。
3. 余额不足时确认出现“充值钱包”。
4. 测试快捷金额和自定义金额。
5. 创建充值单后模拟或完成到账，点击“刷新到账状态”。
6. 确认系统恢复原购买信息并允许钱包支付。
