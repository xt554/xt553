# Fragment Automation V1

This increment adds a fail-closed fulfillment preparation path:

1. Capture a plaintext TON Connect `sendTransaction` object before bridge encryption.
2. Validate destination whitelist, 50 TON single limit and 100 TON global daily limit.
3. Reserve one of three hot wallets.
4. Create an idempotent `ton_transactions` record.
5. Call the signer boundary.

Default configuration is safe mock mode:

```env
FRAGMENT_AUTOMATION_ENABLED=false
TON_SIGNER_MODE=mock
```

Mock mode produces a deterministic `mock_...` external-message hash and never signs or broadcasts funds.

`browser/fragment_hook.js` is a browser probe. Load it with Playwright `add_init_script` before Fragment scripts execute, then read `window.__fragmentTonCaptureV1`. Fragment can change its JavaScript structure; failure to capture must stop the order and trigger manual review. Never treat an encrypted bridge payload as a signable transaction.
