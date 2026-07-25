# Fragment Automation Stage 3

Stage 3 adds dynamic destination policy, canonical TON address comparison, strict raw-message validation, quote-to-chain amount checks, schema approval, isolated real signer support, 3-wallet routing, 50 TON single limit, 100 TON global daily limit, and manual wallet refill.

## Safe rollout

1. Keep `TON_SIGNER_BACKEND=mock` and `FRAGMENT_AUTOMATION_ENABLED=true`.
2. Capture a real order with `expected_amount_nano`; the first schema becomes `MANUAL_REVIEW`.
3. Review and enable the schema in `ton_transaction_schemas`.
4. Run multiple mock orders and reconcile amount, payload hash and destination behavior.
5. Put each mnemonic in `secrets/ton-wallets/ton-hot-N.mnemonic` with mode 0400. Never commit this directory.
6. Set `TON_SIGNER_BACKEND=real`, configure TON Center API key, then restart only the signer.

The signer verifies network, source wallet, limits, TTL and payload hash again. It creates a Wallet V4R2 external message and broadcasts it through TON Center. Broadcast acceptance is not final confirmation; keep orders pending until the chain reconciliation task confirms the outbound message.

## Dynamic destination safety gate

Fragment can generate changing destination addresses. Stage 3 therefore supports a dynamic policy, but a changing address cannot be cryptographically attributed to Fragment merely because the request originated in a browser tab. Real signing is consequently blocked by default when `TON_DESTINATION_POLICY=dynamic`.

After multiple mock captures are reviewed, the operator must explicitly set:

```env
TON_DYNAMIC_REAL_SIGNING_ALLOWED=true
```

This is an acknowledgement switch, not an additional proof of ownership. Keep the 50 TON single limit, 100 TON global daily limit, schema approval, source-wallet match, quote deviation check, and circuit breakers enabled.

## Browser capture boundary

This package contains the pre-encryption browser hook and the protected `/api/v1/internal/fragment/capture` endpoint. Fragment login/session management and page selectors remain deployment-specific because the public website can change. Do not enable unattended real signing until the browser worker has been validated against the live page in mock mode.
