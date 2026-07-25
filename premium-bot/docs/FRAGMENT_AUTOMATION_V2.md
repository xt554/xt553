# Fragment Automation V2

Stage 2 hardens the TON payment preparation layer. It still does **not** contain a real private-key backend.

## Added in V2

- Strict TON Connect validation: mainnet only, bounded TTL, one message, destination whitelist.
- Optional `from` address capture and exact hot-wallet matching.
- Three-wallet routing that excludes wallets with an in-flight transaction.
- Reservation release on signer failure and automatic expiry cleanup through Celery Beat.
- Simulations now use `SIMULATED`; they do not consume wallet balance or daily limits.
- Isolated signer HTTP boundary with HMAC authentication, timestamp, nonce replay protection and idempotency.
- Admin APIs for hot wallets, manual balance sync, destination whitelist, transactions, reservations and circuit breakers.
- Migration `20260725_0004` for signer/capture audit metadata.

## Safe test modes

Local simulation:

```env
FRAGMENT_AUTOMATION_ENABLED=true
TON_SIGNER_MODE=mock
```

Isolated simulation:

```env
FRAGMENT_AUTOMATION_ENABLED=true
TON_SIGNER_MODE=remote_mock
TON_SIGNER_BACKEND=mock
TON_SIGNER_SHARED_SECRET=<long random secret>
TON_SIGNER_WALLET_ADDRESSES=ton-hot-1=EQ...,ton-hot-2=EQ...,ton-hot-3=EQ...
TON_KNOWN_DESTINATIONS=EQ_FRAGMENT_DESTINATION
```

Start the isolated signer profile:

```bash
docker compose --profile telegram --profile fragment up -d --build
```

The signer is not exposed through Nginx or a host port. It is reachable only on the Compose network as `http://signer:9000`.

## Manual wallet balance sync

Use the authenticated admin endpoint:

```http
POST /api/v1/admin/ton/wallets/{wallet_id}/balance
```

The request records an audit log and rejects a balance lower than active reservations.

## Important limitation

`TON_SIGNER_BACKEND=mock` never signs or broadcasts a transaction. Any non-mock backend fails closed. Real key custody and TON message construction belong to Stage 3 after wallet addresses, wallet versions and node providers are confirmed.

## Browser capture probe

`browser/fragment_hook.js` now exposes:

```javascript
window.__fragmentTonCaptureV2
window.__drainFragmentTonCaptures()
```

It uses multiple passive interception points and deduplicates captured requests. It must be injected with Playwright `browser_context.add_init_script()` before Fragment scripts run. Capture failure remains fail-closed; the encrypted bridge body must never be treated as a transaction request.
