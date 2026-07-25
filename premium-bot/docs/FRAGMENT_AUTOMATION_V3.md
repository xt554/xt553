# Fragment Automation V3

V3 completes the controlled production boundary for Fragment + TON:

```text
order quote
  -> reserve one of 3 hot wallets
  -> open the matching browser profile
  -> capture plaintext TON Connect sendTransaction
  -> normalize EQ/UQ/raw addresses
  -> validate quote, structure, TTL, limits and schema
  -> isolated signer
  -> TON Center broadcast
  -> indexed chain reconciliation
  -> Fragment delivery completion
```

## Safety defaults

```env
FRAGMENT_AUTOMATION_ENABLED=false
TON_SIGNER_MODE=remote_mock
TON_SIGNER_BACKEND=mock
TON_NEW_SCHEMA_ACTION=manual_review
```

Mock mode exercises the HMAC signer boundary and idempotency, but never signs or broadcasts TON.

## Dynamic Fragment destinations

Fragment destinations are treated as dynamic. V3 does not approve every destination blindly and does not use `*`. It verifies:

- mainnet network `-239`;
- normalized source equals the reserved hot wallet;
- one ordinary TON message only;
- no `stateInit` and no extra currencies;
- destination workchain is allowed;
- payload is a valid BoC;
- amount is within 1% of a quote captured independently from the payment request;
- single order is at most 50 TON;
- global daily use is at most 100 TON;
- payload/message shape has an administrator-approved schema.

The first occurrence of a new schema enters `MANUAL_REVIEW`. Review it at:

```http
GET   /api/v1/admin/ton/schemas
PATCH /api/v1/admin/ton/schemas/{schema_id}
```

After approval, reopen the payment with the same order and quote. A fresh dynamic destination/payload is accepted only when the approved schema and quoted amount are unchanged; any already-broadcast transaction remains immutable.

## Three browser profiles

Call the reserve endpoint before opening Fragment:

```http
POST /api/v1/internal/fragment/reserve
X-Internal-Token: ...

{"order_id":"...","expected_amount_nano":3850000000}
```

The response returns `ton-hot-1`, `ton-hot-2`, or `ton-hot-3` and its public address. The browser worker must use the profile connected to that exact wallet:

```text
browser profile 1 <-> ton-hot-1
browser profile 2 <-> ton-hot-2
browser profile 3 <-> ton-hot-3
```

Inject `browser/fragment_hook.js` with Playwright `add_init_script()` before loading Fragment. Drain `window.__fragmentTonCaptureV3`, then send the plaintext request with the independently observed quote:

```http
POST /api/v1/internal/fragment/capture

{
  "order_id":"...",
  "expected_amount_nano":3850000000,
  "quote_id":"page-quote-...",
  "request": {"validUntil":...,"network":"-239","from":"UQ...","messages":[...]}
}
```

Do not use the encrypted TON Connect bridge body as the request.

## Signer boundary

The signer is a separate Node container and is not published on a host port. It independently repeats all critical policy checks. Requests use HMAC-SHA256 over:

```text
timestamp + "\n" + nonce + "\n" + raw JSON body
```

Durable signer state is stored in `ton_signer_state`. An idempotency request that is left in `pending` or `unknown` is never automatically rebroadcast.

### Real key files

Real backend files are named:

```text
secrets/ton-wallets/ton-hot-1.mnemonic
secrets/ton-wallets/ton-hot-2.mnemonic
secrets/ton-wallets/ton-hot-3.mnemonic
```

Each file contains exactly 24 mnemonic words. Never put them in `.env`, Git, chat, API payloads, browser storage, or database tables. On Linux, set owner UID 10001 and mode 0400:

```bash
sudo chown 10001:10001 secrets/ton-wallets/*.mnemonic
sudo chmod 0400 secrets/ton-wallets/*.mnemonic
```

The signer derives a V4R2 address and refuses to run a transaction when it differs from `TON_SIGNER_WALLET_ADDRESSES`.

## Chain confirmation and delivery are separate

`BROADCASTED` only means the external message was submitted. Celery checks TON Center v3 and verifies the wallet account, destination and amount. Only then does the transaction become `CONFIRMED`.

Premium delivery is completed separately:

```http
POST /api/v1/internal/fragment/complete

{"order_id":"...","status":"SUCCESS","reference":"fragment-reference"}
```

A Fragment failure after broadcast or confirmation enters `MANUAL_REVIEW`; it does not trigger an automatic refund or second TON payment.

## Production backend

After mock validation:

```env
TON_SIGNER_MODE=remote
TON_SIGNER_BACKEND=toncenter_v4r2
ALLOW_MOCK_TON_SIGNER_IN_PRODUCTION=false
TON_ALLOW_MOCK_FRAGMENT_COMPLETION=false
```

Manual refill remains enabled. V3 never transfers funds from a cold wallet into hot wallets.
