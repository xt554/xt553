# Fragment + TON Stage 3 deployment

This package adds the database and fail-closed risk layer for:

- exactly **3 TON hot wallets**;
- **50 TON maximum per transaction**;
- **100 TON maximum platform spend per UTC day**;
- wallet rotation through database row locking;
- destination allow-listing;
- circuit breakers;
- **manual hot-wallet refill only**.

It does **not** embed wallet seeds or automatically sign transactions. The included signer boundary rejects every request until a separately isolated signer is connected.

## 1. Environment

Add to `.env`:

```env
FRAGMENT_AUTOMATION_ENABLED=false
TON_HOT_WALLET_COUNT=3
TON_SINGLE_LIMIT=50
TON_GLOBAL_DAILY_LIMIT=100
TON_WALLET_DAILY_LIMIT=100
TON_MANUAL_REFILL=true
TON_WALLET_LOCK_SECONDS=240
TON_RESERVATION_MINUTES=10
TON_CIRCUIT_FAILURE_THRESHOLD=3
TON_CIRCUIT_COOLDOWN_SECONDS=900
TON_KNOWN_DESTINATIONS=EQ_verified_fragment_destination

TON_WALLET_1_ADDRESS=EQ_public_address_1
TON_WALLET_2_ADDRESS=EQ_public_address_2
TON_WALLET_3_ADDRESS=EQ_public_address_3
```

Keep `FRAGMENT_AUTOMATION_ENABLED=false` until the Fragment payment parser, chain verifier, and isolated signer have been tested together.

## 2. Migrate and seed wallet metadata

```bash
docker compose run --rm migrate alembic upgrade head
docker compose run --rm api python scripts/seed_ton_wallets.py
```

Only public wallet addresses are stored. Never place seed phrases in `.env`, Compose, source code, Redis, MySQL, browser profiles, or Celery task arguments.

## 3. Manual refill policy

Refill each wallet manually from a separate treasury wallet. Suggested operating band:

```text
minimum: 1 TON
working target: 50 TON
hard metadata maximum: 100 TON
```

The router will not allocate an order when the available balance cannot cover the payment plus the minimum reserve. Balance values must be refreshed by a chain-balance worker before enabling automation.

## 4. Safety behavior

The payment risk service rejects a transaction when:

- automation is disabled;
- amount is zero or above 50 TON;
- destination is not enabled in `payment_whitelist`;
- destination-specific limit is exceeded;
- confirmed/broadcast/signing spend would push the UTC daily total above 100 TON.

The wallet router:

- uses `FOR UPDATE SKIP LOCKED`;
- returns an existing reservation for the same order;
- excludes paused/disabled wallets;
- enforces wallet single and daily limits;
- reserves balance before signing;
- fails closed when all three wallets lack capacity.

## 5. Remaining production integrations

Before changing `FRAGMENT_AUTOMATION_ENABLED=true`, implement and test:

1. Fragment browser parser that extracts destination, amount, payload and expiry.
2. Independent validation of the extracted destination and amount.
3. Isolated signer over mTLS; API and Celery containers must never read private keys.
4. TON broadcast and dual-source chain verification.
5. Reservation consume/release jobs and expired-reservation cleanup.
6. Daily wallet-spend reset/rollover and on-chain balance synchronization.
7. Admin controls for pausing wallets and opening the global circuit breaker.
8. Reconciliation for broadcasted transactions before any refund or retry.

## 6. Rollout

Start with `FRAGMENT_AUTOMATION_ENABLED=false` and exercise the pipeline in dry-run mode. Then enable one wallet with a low balance, followed by all three wallets after transaction matching and circuit-breaker behavior are verified. The 50/100 TON limits are hard upper bounds, not recommended initial live exposure.
