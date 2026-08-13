# Drop your product photos here

Put image files in these folders and run one command to load them into the app.

```
backend/images/
  categories/   <- one picture per category
  items/        <- one photo per item
```

## How to name the files

Name each file after the category or item it belongs to. The extension can be
`.png`, `.jpg`, `.jpeg` or `.webp`.

```
images/categories/Dairy.png
images/categories/Personal Care.png
images/items/Rice.jpg
images/items/Toor Dal.png
```

Matching ignores case, spaces, hyphens and underscores, so these all work for
the item **Red Chilli Powder**:

```
Red Chilli Powder.png
red-chilli-powder.png
red_chilli_powder.PNG
```

## Load them into the app

From the `backend` folder, with the virtual environment active:

```bash
python manage.py import-images
```

Check what would happen first, without changing anything:

```bash
python manage.py import-images --dry-run
```

Only load one folder:

```bash
python manage.py import-images --only categories
python manage.py import-images --only items
```

Each image is resized to a max of 512px and re-encoded as JPEG before being
stored in the database, so large photos are fine — they get compressed
automatically. Re-running the command replaces any picture already set.

Files whose name doesn't match a category or item are listed at the end so you
can rename them and run it again.
