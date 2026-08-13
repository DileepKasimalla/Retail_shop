# Deploying online (hosted)

This app is built to move from local to the cloud without code changes — only
environment variables differ. Below is a safe, minimal production setup.

## Overview

- **Backend**: FastAPI served by `uvicorn`, behind HTTPS (a reverse proxy or the
  host platform provides TLS). Use **PostgreSQL** in production, not SQLite.
- **Frontend**: static files built by `npm run build`, served by any static host
  or CDN. It talks to the backend over HTTPS.

## 1. Database (PostgreSQL)

Provision a Postgres database (e.g. Render, Railway, Supabase, RDS, Neon). Then
set on the backend:

```
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
```

Install the driver (uncomment in `requirements.txt` or install directly):

```bash
pip install "psycopg[binary]"
```

Tables are created automatically on first start. For schema changes over time,
consider adding Alembic migrations.

## 2. Backend environment (production)

Set these as real environment variables on your host (never commit them):

```
ENVIRONMENT=production
SECRET_KEY=<48+ char random string>     # python -c "import secrets; print(secrets.token_urlsafe(48))"
ACCESS_TOKEN_EXPIRE_MINUTES=720
DATABASE_URL=postgresql+psycopg://...
CORS_ORIGINS=https://your-frontend-domain.com
CURRENCY_CODE=INR
CURRENCY_SYMBOL=₹
```

> The app **refuses to start in production without a strong `SECRET_KEY`.**

Run with a production server command, e.g.:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

Create the shopkeeper account once (from a shell on the host):

```bash
python manage.py create-admin
```

## 3. Frontend build

Set the backend URL at build time and build:

```bash
cd frontend
echo "VITE_API_BASE_URL=https://your-backend-domain.com" > .env.production
npm ci
npm run build
```

Deploy the generated `frontend/dist/` folder to any static host (Netlify,
Vercel, Cloudflare Pages, S3+CloudFront, Nginx, etc.).

If the host does client-side routing, add a **SPA fallback** so unknown paths
serve `index.html` (e.g. Netlify `_redirects`: `/*  /index.html  200`).

## 4. Security checklist for hosting

- [ ] HTTPS everywhere (TLS at the proxy / platform).
- [ ] Strong, secret `SECRET_KEY`, stored only in the host's secret manager.
- [ ] `CORS_ORIGINS` set to your exact frontend domain (no wildcards).
- [ ] PostgreSQL with a strong password, not publicly reachable.
- [ ] Regular database backups.
- [ ] Change the shopkeeper password after first login (Settings page).
- [ ] Consider a WAF / platform rate limiting in front of the API.

## Notes

- The built-in login throttle is per-process and in-memory. With multiple
  workers/instances, add rate limiting at the proxy/load balancer for full
  protection.
- Tokens are stateless JWTs. To force logout of all sessions, rotate
  `SECRET_KEY` (this invalidates every existing token).
