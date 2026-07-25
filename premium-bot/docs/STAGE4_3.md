
# Stage 4.3 Production Fragment Runner

Stage 4.3 upgrades the Stage 4.2 polling runner into an observable, recoverable browser executor. It still does not place TON private keys in the browser container.

## Delivered capabilities

- Persistent Chromium profiles and explicit `storage_state.json` snapshots.
- Automatic login-expiry detection and Telegram administrator alerts.
- Selector registry and pre-flight DOM self-checks.
- Failure screenshot, HTML snapshot, browser console export, and Playwright Trace recording.
- Exponential retry backoff with per-job attempt limits.
- Multiple Fragment accounts with database leases and priority rotation.
- Local runner health endpoints on port `9100` and Docker health checks.
- Database-backed runner heartbeat, stale-runner monitoring, and automatic expired-lease release.
- Admin dashboard for runners, accounts, jobs, errors, and diagnostic downloads.

## Safe defaults

Keep the first deployment in observation mode:

```env
FRAGMENT_RUNNER_MODE=observe
FRAGMENT_RUNNER_AUTO_CLICK=false
TON_SIGNER_MODE=remote_mock
TON_SIGNER_BACKEND=mock
TON_DYNAMIC_REAL_SIGNING_ALLOWED=false
```

Observation mode opens and validates the Fragment purchase page but deliberately refuses to click the purchase button. The task moves to manual review with a trace and screenshot when available.

## Account profiles

Configure accounts as `code=profile-directory`, separated by commas:

```env
FRAGMENT_RUNNER_ACCOUNTS=fragment-01=fragment-01,fragment-02=fragment-02
```

Each account receives an isolated persistent profile under:

```text
/data/profiles/<profile-name>/
```

No Fragment password is stored in the database. Cookies, local storage, IndexedDB, and the explicit `storage_state.json` remain inside the Docker volume.

## Administrator alerts

```env
FRAGMENT_RUNNER_ALERT_CHAT_IDS=123456789,987654321
FRAGMENT_RUNNER_ALERT_COOLDOWN_SECONDS=900
```

The existing Telegram bot token is used only to send operational alerts. Login expiration, selector drift, and stale runner events are rate limited.

## Diagnostics

Artifacts are stored in a shared volume:

```text
/data/fragment-artifacts/YYYYMMDD/<job-id>/
```

Possible files:

- `failure.png`
- `failure-trace.zip` or `trace.zip`
- `page.html`
- `console.json`

The API mounts the volume read-only and exposes authenticated administrator download endpoints. Paths are canonicalized and constrained to the artifact root.

## Health

Inside the runner container:

```text
GET http://127.0.0.1:9100/health/live
GET http://127.0.0.1:9100/health/ready
```

The runner also reports status to the API every `FRAGMENT_RUNNER_HEARTBEAT_SECONDS`. Celery marks stale instances offline after `FRAGMENT_RUNNER_STALE_SECONDS` and releases expired account leases.

## Deployment

```bash
cd /www/wwwroot/premium-bot

docker compose \
  --profile telegram \
  --profile fragment \
  --profile fragment-runner \
  up -d --build
```

Expected migration:

```text
20260725_0008 -> 20260725_0009
```

Check:

```bash
docker compose ps
docker compose logs --tail=150 migrate
docker compose logs --tail=150 fragment-runner
docker compose exec fragment-runner python -c "import sqlalchemy, playwright; print('runner dependencies ok')"
```

## Enabling automatic interaction

Do not enable automatic clicks until all selectors are verified against the live Fragment page and several mock-signing captures have been reviewed.

```env
FRAGMENT_RUNNER_MODE=auto
FRAGMENT_RUNNER_AUTO_CLICK=true
```

A selector failure stops the task and raises an alert instead of guessing or clicking a broad element.

## Initial login and live-site validation

Persistent profiles retain an already authenticated Fragment session; they do not bypass Fragment authentication. A new account without an existing browser profile is marked `LOGIN_REQUIRED`, stops taking actions, and raises an administrator alert.

Provision the first authenticated profile only in a controlled interactive browser environment. After login succeeds, keep the profile directory under the `fragment_profiles` Docker volume and return the runner to headless mode. Never store a Fragment password, wallet seed phrase, or TON private key in `.env`, the database, or the runner image.

The supplied selector registry is deliberately conservative. Validate it against the current live Fragment page in `observe` mode before setting `FRAGMENT_RUNNER_MODE=auto` or enabling automatic clicks.
