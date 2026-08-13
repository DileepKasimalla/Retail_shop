"""Small management CLI for the shop backend.

Usage:
    python manage.py init-db                      # create any missing tables
    python manage.py create-admin [username]      # create/prompt a shopkeeper account
    python manage.py reset-password <username>    # set a new password
    python manage.py list-users
    python manage.py import-images [--dry-run] [--only categories|items]
        Load photos from backend/images/ into the app. See images/README.md.
"""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import CategoryImage, Product, User
from app.security import hash_password

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGES_DIR = Path(__file__).parent / "images"


def _ensure_tables() -> None:
    Base.metadata.create_all(bind=engine)


def init_db() -> None:
    """Create the schema. Run this once against a hosted DB after deploying,
    since serverless skips create_all on startup."""
    _ensure_tables()
    with engine.connect() as conn:
        target = conn.engine.url.render_as_string(hide_password=True)
    print(f"Schema is up to date on {target}")


def _prompt_password() -> str:
    while True:
        pw = getpass.getpass("New password (min 8 chars): ")
        if len(pw) < 8:
            print("  Password too short. Try again.")
            continue
        confirm = getpass.getpass("Confirm password: ")
        if pw != confirm:
            print("  Passwords do not match. Try again.")
            continue
        return pw


def create_admin(username: str | None) -> None:
    _ensure_tables()
    username = (username or input("Username: ")).strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == username)):
            print(f"User '{username}' already exists. Use reset-password instead.")
            sys.exit(1)
        pw = _prompt_password()
        db.add(User(username=username, hashed_password=hash_password(pw)))
        db.commit()
        print(f"Created shopkeeper account '{username}'.")


def reset_password(username: str) -> None:
    _ensure_tables()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if not user:
            print(f"No such user: {username}")
            sys.exit(1)
        user.hashed_password = hash_password(_prompt_password())
        db.add(user)
        db.commit()
        print(f"Password updated for '{username}'.")


def list_users() -> None:
    _ensure_tables()
    with SessionLocal() as db:
        users = db.scalars(select(User)).all()
        if not users:
            print("(no users)")
            return
        for u in users:
            print(f"  #{u.id}  {u.username}  active={u.is_active}")


def _norm(text: str) -> str:
    """Loose key so 'Red Chilli Powder', 'red-chilli-powder' and
    'red_chilli_powder' all match."""
    return re.sub(r"[\s\-_]+", " ", (text or "").strip().lower())


def _suggest(stem: str, known: dict[str, str]) -> str:
    """' (did you mean X?)' when a filename is a near miss — catches typos."""
    import difflib

    close = difflib.get_close_matches(_norm(stem), list(known), n=1, cutoff=0.7)
    return f"  (did you mean “{known[close[0]]}”?)" if close else ""


def _image_files(folder: Path) -> list[Path]:
    """Image files in a folder. When several files map to the same name (e.g.
    Shampoo.jpg and Shampoo.png) the most recently saved one wins."""
    if not folder.is_dir():
        return []
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    chosen: dict[str, Path] = {}
    for path in files:
        key = _norm(path.stem)
        current = chosen.get(key)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            if current is not None:
                print(f"  note: {path.name} and {current.name} both match — using the newer one")
            chosen[key] = path
        else:
            print(f"  note: {path.name} and {current.name} both match — using the newer one")
    return sorted(chosen.values())


def import_images(dry_run: bool = False, only: str | None = None) -> None:
    """Load photos from backend/images/{categories,items} into the database."""
    _ensure_tables()
    from app.imaging import process_image  # imported here so Pillow stays optional

    total_ok = 0
    unmatched: list[str] = []

    with SessionLocal() as db:
        # ---- categories ----
        if only in (None, "categories"):
            files = _image_files(IMAGES_DIR / "categories")
            known = {
                _norm(c): c
                for (c,) in db.execute(select(Product.category).distinct()).all()
            }
            print(f"\nCategories ({len(files)} file(s) found):")
            if not files:
                print("  (no images in images/categories)")
            for path in files:
                target = known.get(_norm(path.stem))
                if target is None:
                    hint = _suggest(path.stem, known)
                    unmatched.append(f"categories/{path.name}{hint}")
                    print(f"  --   {path.name}  -> no category with that name{hint}")
                    continue
                try:
                    data, ctype = process_image(path.read_bytes())
                except Exception as e:  # noqa: BLE001 - report and continue
                    print(f"  FAIL {path.name}  -> {e}")
                    continue
                if dry_run:
                    print(f"  would set {target!r} from {path.name} ({len(data)} bytes)")
                else:
                    row = db.execute(
                        select(CategoryImage).where(CategoryImage.name == target)
                    ).scalar_one_or_none()
                    if row is None:
                        row = CategoryImage(name=target, image_data=data, image_type=ctype)
                    else:
                        row.image_data, row.image_type = data, ctype
                    db.add(row)
                    db.commit()
                    print(f"  OK   {target:20} <- {path.name} ({len(data)} bytes)")
                total_ok += 1

        # ---- items ----
        if only in (None, "items"):
            files = _image_files(IMAGES_DIR / "items")
            products = db.execute(select(Product)).scalars().all()
            by_name: dict[str, Product] = {_norm(p.name): p for p in products}
            print(f"\nItems ({len(files)} file(s) found):")
            if not files:
                print("  (no images in images/items)")
            for path in files:
                product = by_name.get(_norm(path.stem))
                if product is None:
                    hint = _suggest(path.stem, {_norm(p.name): p.name for p in products})
                    unmatched.append(f"items/{path.name}{hint}")
                    print(f"  --   {path.name}  -> no item with that name{hint}")
                    continue
                try:
                    data, ctype = process_image(path.read_bytes())
                except Exception as e:  # noqa: BLE001
                    print(f"  FAIL {path.name}  -> {e}")
                    continue
                if dry_run:
                    print(f"  would set {product.name!r} from {path.name} ({len(data)} bytes)")
                else:
                    product.image_data, product.image_type = data, ctype
                    db.add(product)
                    db.commit()
                    print(f"  OK   {product.name:20} <- {path.name} ({len(data)} bytes)")
                total_ok += 1

    print()
    if dry_run:
        print(f"Dry run: {total_ok} image(s) would be imported. Nothing was changed.")
    else:
        print(f"Imported {total_ok} image(s).")
    if unmatched:
        print(f"\n{len(unmatched)} file(s) did not match any category/item name:")
        for name in unmatched:
            print(f"  - {name}")
        print("Rename them to match exactly, then run the command again.")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    cmd, *rest = args
    if cmd == "init-db":
        init_db()
    elif cmd == "create-admin":
        create_admin(rest[0] if rest else None)
    elif cmd == "reset-password":
        if not rest:
            print("Usage: python manage.py reset-password <username>")
            sys.exit(1)
        reset_password(rest[0])
    elif cmd == "list-users":
        list_users()
    elif cmd == "import-images":
        only = None
        if "--only" in rest:
            idx = rest.index("--only")
            if idx + 1 >= len(rest) or rest[idx + 1] not in ("categories", "items"):
                print("Usage: python manage.py import-images [--dry-run] [--only categories|items]")
                sys.exit(1)
            only = rest[idx + 1]
        import_images(dry_run="--dry-run" in rest, only=only)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
