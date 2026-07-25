# Stage 4.2 — Fragment Runner

Stage 4.2 adds a leased Fragment browser-job queue and an isolated Playwright runner. The runner has no TON private keys and submits plaintext TON Connect requests to the API risk boundary.

Default mode is `observe`; it will not click purchase controls. Use it to bootstrap and preserve authenticated browser profiles. Automatic clicking requires explicit selectors and `FRAGMENT_RUNNER_AUTO_CLICK=true`. Real signing remains disabled independently.

Start with:

```bash
docker compose --profile telegram --profile fragment --profile fragment-runner up -d --build
```

Required environment variables are documented in `.env.example`. Keep `TON_SIGNER_BACKEND=mock` and `TON_DYNAMIC_REAL_SIGNING_ALLOWED=false` during validation.
