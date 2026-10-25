# Bitmini

Bitmini is a custom blockchain wallet and app experience built around a sovereign token model, encrypted wallet secrets, identity-aware onboarding, and a mobile-first dashboard. The project is intentionally structured as a hybrid custody prototype: custodial default for support and recovery, optional self-custody paths for advanced users, and clear boundaries around what remains a beta product versus a regulated launch.

## Included in this workspace

- Responsive wallet dashboard and app shell
- Identity-based registration with username and wallet ID generation
- Encrypted wallet secret handling and session-based authorization
- Supply cap enforcement and genesis reserve protections
- Referral rewards and admin role checks
- Deployment-aware buy/sell messaging where real-money integrations are disabled until provider configuration is complete
- Simple deployment-ready Flask app configuration

## Production configuration

Use environment variables instead of hardcoded runtime values:

```bash
export BITMINI_ENV=production
export PORT=8000
export BITMINI_SECRET_KEY="replace-with-a-strong-random-secret"
export BITMINI_DB_PATH="/var/lib/bitmini/bitmini.db"
export BITMINI_NODE_RPC_URL="https://your-node.example.com"
```

The app automatically enables stricter cookie and header settings in production mode, and the startup path disables debug mode and reloader behavior for normal deployment.

## Run locally

```bash
Set-Location 'D:\Bitmini'
$env:BITMINI_ENV='production'
$env:PORT='8000'
$env:BITMINI_SECRET_KEY='bitmini-local-secret-change-me'
.\.venv\Scripts\python.exe app.py
```

Then visit:

```text
http://localhost:8000/app
```

## Production deployment

For a production environment, run the app behind a WSGI server such as Gunicorn:

```bash
gunicorn --bind 0.0.0.0:8000 app:app
```

This is the recommended server layer instead of Flask's built-in development server.

## Security and policy notes

- Only the genesis wallet holds the admin role by default.
- Regular wallets cannot access admin endpoints without role assignment.
- Real-money purchase integrations are intentionally blocked unless a payment provider and operating policy are enabled.
- All write actions require a valid signed wallet session and, when applicable, explicit wallet authentication.
- The product follows a staged hybrid custody model rather than claiming full self-custody by default.
- KYC, AML, sanctions screening, and admin risk controls are exposed as review and governance endpoints.
- Supply and referral caps are enforced in backend logic.
- Error responses are standardized and security headers are applied.

## Legal-ready launch boundaries

See [docs/legal-launch-checklist.md](docs/legal-launch-checklist.md) for the launch gates, deployment checklist, and operational boundaries before any live customer rollout.

## Status

The application is now structured as a safer, more deployable foundation with explicit production controls, policy enforcement, and a clean runtime configuration model.
