# Stage 4.1 — Safe fulfillment state machine

This release removes mock-success fulfillment. A wallet payment now stops at `WAIT_FRAGMENT` until a real provider/Fragment runner verifies delivery.

States: `WAIT_PAY → PAID → PROCESSING → WAIT_FRAGMENT → WAIT_SIGN → BROADCASTED → CONFIRMING → COMPLETED`. Failures use `FAILED`, `REFUNDED`, or `MANUAL_REVIEW`.

Internal-wallet failures are refunded idempotently with the existing wallet ledger key. Only `COMPLETED` sends the confirmed-success user message.

Deploy with Alembic revision `20260725_0007`. Keep `PREMIUM_PROVIDER=mock` for safety; mock orders will remain in `WAIT_FRAGMENT` instead of becoming completed.
