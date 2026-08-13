# Retail Shop Manager

A simple, secure web app for a retail shopkeeper to manage customers, the bills
they run up (debts), and the payments they make. Each customer has a **ledger**:
a *bill* increases what they owe, a *payment* reduces it, and the app always
shows the running **balance** — per customer and shop-wide.

- **Backend:** Python + FastAPI + SQLAlchemy (SQLite by default, Postgres-ready)
- **Frontend:** React + TypeScript + Vite
- **Auth:** single shopkeeper login (JWT + bcrypt). Only the logged-in shopkeeper
  can view or change anything.
- **Currency:** Indian Rupee (₹)

---

## What it does

- **Login** — only the shopkeeper can access the app.
- **Dashboard** — total outstanding dues, collected this month, billed this
  month, customer count, and top debtors.
- **Customers** — add / edit / delete, search by name or phone, filter to only
  those who owe money. "Per use" vs "Periodic (monthly)" payment types.
- **Customer ledger** — add bills, record payments, see every entry with a
  running balance, delete entries. Delete a customer (with all history) or mark
  them inactive to hide them while keeping the record.
- **Settings** — change the shopkeeper password.

---

## Prerequisites

- **Python 3.11+** (tested on 3.14) — already installed.
- **Node.js 18+** — required for the React frontend.
  Download the "LTS" installer from <https://nodejs.org> and install it, then
  **open a new terminal** so `node` and `npm` are on your PATH.

---

## 1. Run the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell/CMD
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
```

Create your environment file and set a real secret key:

```bash
copy .env.example .env            # Windows
# cp .env.example .env            # macOS/Linux
```

Generate a strong secret and paste it into `.env` as `SECRET_KEY=`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Create the shopkeeper account:

```bash
python manage.py create-admin
```

Start the API:

```bash
uvicorn app.main:app --reload
```

The API runs at <http://127.0.0.1:8000> — interactive docs at
<http://127.0.0.1:8000/docs>.

## 2. Run the frontend

In a **second terminal**:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173> and log in with the account you created.
(In development, the frontend automatically proxies `/api` calls to the backend,
so no extra configuration is needed.)

---

## Management commands

```bash
python manage.py create-admin [username]   # create the shopkeeper account
python manage.py reset-password <username> # set a new password
python manage.py list-users
python manage.py import-images             # load photos from backend/images/
```

## Adding product photos in bulk

Drop image files into `backend/images/` and import them in one command:

```
backend/images/
  categories/Dairy.png
  categories/Personal Care.png
  items/Rice.jpg
  items/Toor Dal.png
```

```bash
python manage.py import-images --dry-run   # preview, changes nothing
python manage.py import-images             # load them
```

File names are matched to category/item names ignoring case, spaces, hyphens and
underscores (`red-chilli-powder.png` matches **Red Chilli Powder**). Images are
resized to 512px and stored in the database. See
[backend/images/README.md](backend/images/README.md) for details.

You can also add photos one at a time in the app (Edit item → **Add photo**, or
hover a category tile → **✎**), or paste an image link.

---

## Security notes

- Passwords are hashed with **bcrypt**; only the hash is ever stored.
- API access requires a **JWT** bearer token; every data endpoint is protected.
- Login has a basic **per-IP throttle** to slow brute-force attempts.
- `SECRET_KEY` is **required in production** — the app refuses to start without a
  strong one.
- CORS is locked to the origins listed in `CORS_ORIGINS`.
- All input is validated by Pydantic; database access uses parameterized ORM
  queries (no SQL injection).

See [DEPLOY.md](DEPLOY.md) for hosting the app online safely.
