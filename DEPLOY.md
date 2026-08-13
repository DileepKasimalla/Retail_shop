# Deploying to Vercel + Neon

The repo is already configured for this. Frontend and backend go to the **same
Vercel project on one domain**: static files from `frontend/dist`, and the
FastAPI app as a Python function that `vercel.json` rewrites `/api/*` onto.

Because they share an origin, `VITE_API_BASE_URL` stays **blank** and CORS never
comes into play — the browser only ever talks to one host.

```
your-shop.vercel.app/            -> frontend/dist/index.html   (static)
your-shop.vercel.app/api/...     -> api/index.py -> FastAPI     (function)
```

---

## 1. Push to GitHub

The repo is initialised with one commit on `main`. Create an **empty** GitHub
repo (no README/licence), then:

```bash
git remote add origin https://github.com/<you>/retail-shop.git
git push -u origin main
```

## 2. Create the database (Neon)

Sign up at [neon.tech](https://neon.tech) and create a project. Neon gives you
**two** connection strings — you need both, for different jobs:

| Which | Host contains | Use it for |
|---|---|---|
| **Pooled** | `-pooler` | `DATABASE_URL` on Vercel (runtime) |
| **Direct** | no `-pooler` | the one-off migration + admin commands below |

Serverless functions must use the pooled endpoint: each cold container opens its
own connection, and without the pooler they exhaust Neon's connection limit.
The migration uses the direct endpoint because pgbouncer dislikes long `COPY`
transactions.

## 3. Move your existing data across

`scripts/migrate-to-neon.ps1` creates the schema on Neon and copies every table
(customers, products, ledger entries, bill items, bill payments, users, and the
photo `bytea` columns) in foreign-key order, then fixes the id sequences.

```powershell
.\scripts\migrate-to-neon.ps1 -TargetUrl "postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require"
```

Use the **direct** URL. The script refuses to run if the target already has
rows, so it is safe to re-read before committing to it.

> It migrates *data only* on purpose. The local server is Postgres 18 and
> Neon's newest is 17, so a schema dump from 18 can contain syntax 17 rejects.
> SQLAlchemy creates the schema instead, and the data restores as plain `COPY`
> blocks, which are version-agnostic.

## 4. Import the project into Vercel

**Add New → Project → import the GitHub repo.** Vercel reads `vercel.json`, so
leave the framework preset alone. Set these environment variables (Settings →
Environment Variables, applied to Production):

```
ENVIRONMENT=production
SECRET_KEY=<paste a fresh one, see below>
DATABASE_URL=postgresql+psycopg://user:pass@ep-xxx-pooler.neon.tech/neondb?sslmode=require
ACCESS_TOKEN_EXPIRE_MINUTES=720
CURRENCY_CODE=INR
CURRENCY_SYMBOL=₹
SHOP_NAME=<your shop's name, printed on bill PDFs>
SHOP_ADDRESS=
SHOP_PHONE=
```

Generate the secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Two things to get right:

- Keep the `postgresql+psycopg://` scheme — that is SQLAlchemy's driver prefix,
  not plain libpq. Neon hands you `postgresql://`, so add the `+psycopg`.
- Use the **pooled** host here (the one with `-pooler`).

The app refuses to boot in production if `SECRET_KEY` is missing or under 32
characters, so a bad value fails loudly rather than silently weakening tokens.

`CORS_ORIGINS` can stay at its default — same-origin requests never trigger a
CORS check. Only set it if you later serve the frontend from another domain.

## 5. Create your login

Vercel has no shell, so run this from your machine pointed at Neon (**direct**
URL). PowerShell:

```powershell
cd backend
$env:DATABASE_URL = "postgresql+psycopg://user:pass@ep-xxx.neon.tech/neondb?sslmode=require"
.\.venv\Scripts\python.exe manage.py create-admin
Remove-Item Env:\DATABASE_URL
```

If you migrated in step 3 your existing login came across already — use
`manage.py list-users` to check, and `reset-password` if you need to.

## 6. Verify

- `https://your-shop.vercel.app/api/health` → `{"status":"ok"}`
- Log in, open a customer, add a bill, print a PDF
- Check the Items page shows photos (proves `bytea` survived the migration)

---

## Known constraint: function timeout

Vercel functions are capped at **60s** (`maxDuration` in `vercel.json`; the
Hobby plan's default is 10s). Almost everything is far inside that, but two
paths can exceed it:

- **Bulk CSV/XLSX import** near the 5000-row cap — each row may decode an image.
- **`POST /products/{id}/image/from-url`** — an 8s fetch timeout per image, so a
  batch of slow hosts adds up.

Both are one-off admin jobs, so the workaround is to run them against the hosted
DB from your machine instead of through the deployed site — same
`$env:DATABASE_URL` trick as step 5, then `manage.py import-images`. For CSV
uploads through the UI, split the file into chunks of a few hundred rows.

If a deploy rejects `maxDuration: 60`, your plan doesn't allow it — drop the
line from `vercel.json` and it falls back to the plan default.

## Other notes

- **Cold starts.** The first request after idle takes a second or two while the
  Python function boots. Normal for serverless; subsequent requests are fast.
- **Schema changes.** `create_all` is skipped on serverless (it would re-run on
  every cold start). After changing a model, run `manage.py init-db` against
  Neon. That only *adds* missing tables — it never alters an existing one, so
  for column changes either write the `ALTER` yourself or add Alembic.
- **Backups.** Neon keeps point-in-time history on paid plans; on the free plan
  take your own dumps periodically.
- **Login throttle** is per-process and in-memory, so it resets as containers
  recycle. Add rate limiting at the edge if you need a hard guarantee.
- **Rotating `SECRET_KEY`** invalidates every existing token — that is how you
  force-logout all sessions.

---

## Deploying somewhere else

Nothing in the app is Vercel-specific; only environment variables change. For a
container/VM host, ignore `vercel.json` and `api/`, then:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2   # from backend/
```

Serve `frontend/dist` from any static host, built with
`VITE_API_BASE_URL=https://your-backend-domain.com`, and set `CORS_ORIGINS` to
the frontend's exact origin (no wildcards) since it is no longer same-origin.
Add a SPA fallback so unknown paths serve `index.html`.

### Security checklist

- [ ] HTTPS everywhere (automatic on Vercel).
- [ ] Strong `SECRET_KEY`, stored only in the host's secret manager.
- [ ] `CORS_ORIGINS` pinned to exact origins if not same-origin.
- [ ] Database not publicly reachable without TLS (`sslmode=require`).
- [ ] Regular database backups.
- [ ] Change the shopkeeper password after first login (Settings page).
