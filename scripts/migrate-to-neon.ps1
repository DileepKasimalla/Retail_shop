<#
.SYNOPSIS
    Copy the local Retail_shop database into a hosted Postgres (Neon).

.DESCRIPTION
    Data-only migration. The schema is created on the target by SQLAlchemy
    itself (`python manage.py init-db`) rather than by pg_dump, for two
    reasons:

      1. The local server is Postgres 18 and Neon's newest is 17. A schema
         dump from 18 can contain syntax 17 rejects; a *data* dump is plain
         COPY blocks and restores across versions cleanly.
      2. The app is the authority on its own schema, so what lands on the
         target is exactly what the code expects.

    Tables are dumped one at a time in foreign-key dependency order, because
    `pg_dump --data-only` does not guarantee a FK-safe ordering on its own and
    Neon roles lack the superuser rights that --disable-triggers needs.

    Bytea columns (product photos, category photos) are included.

.PARAMETER TargetUrl
    Target connection string in libpq form, e.g.
      postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
    Use Neon's DIRECT (non-pooled) endpoint here — pgbouncer does not like
    long COPY transactions.

.PARAMETER Force
    Migrate even if the target already has rows (data is appended, which will
    usually collide on primary keys). Without this the script stops.

.EXAMPLE
    .\scripts\migrate-to-neon.ps1 -TargetUrl "postgresql://...neon.tech/neondb?sslmode=require"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$TargetUrl,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repo 'backend'
$python = Join-Path $backend '.venv\Scripts\python.exe'

# Tables in FK dependency order: parents before children.
$TABLES = @(
    'users',
    'customers',
    'products',
    'category_images',
    'ledger_entries',   # -> customers
    'bill_items',       # -> ledger_entries, products
    'bill_payments'     # -> ledger_entries
)

# ---------------------------------------------------------------- tooling ---
$pgBin = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe' -ErrorAction SilentlyContinue |
         Sort-Object { [int]($_.Directory.Parent.Name) } -Descending |
         Select-Object -First 1
if (-not $pgBin) { throw "pg_dump.exe not found under C:\Program Files\PostgreSQL\*\bin" }
$pgDump = $pgBin.FullName
$psql = Join-Path $pgBin.Directory.FullName 'psql.exe'
if (-not (Test-Path $psql)) { throw "psql.exe not found next to pg_dump" }
if (-not (Test-Path $python)) { throw "venv python not found at $python" }

Write-Host "pg_dump : $pgDump"
Write-Host "psql    : $psql`n"

# ------------------------------------------------- source connection string ---
# Read DATABASE_URL from backend/.env and convert SQLAlchemy's
# postgresql+psycopg:// scheme to the postgresql:// libpq tools expect.
$envFile = Join-Path $backend '.env'
if (-not (Test-Path $envFile)) { throw "backend/.env not found - cannot determine the source database" }
$line = Select-String -Path $envFile -Pattern '^\s*DATABASE_URL\s*=\s*(.+)$' | Select-Object -First 1
if (-not $line) { throw "DATABASE_URL not set in backend/.env" }
$sourceUrl = $line.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
$sourceUrl = $sourceUrl -replace '^postgresql\+psycopg://', 'postgresql://'
if ($sourceUrl -match '^sqlite') { throw "Source is SQLite, not Postgres. Nothing to migrate with pg_dump." }

$masked = $sourceUrl -replace '(://[^:]+:)[^@]+@', '${1}***@'
Write-Host "source  : $masked"
$maskedTarget = $TargetUrl -replace '(://[^:]+:)[^@]+@', '${1}***@'
Write-Host "target  : $maskedTarget`n"

# ------------------------------------------------------ 1. create schema ---
Write-Host '== 1/4  Creating schema on the target ==' -ForegroundColor Cyan
$prevUrl = $env:DATABASE_URL
# SQLAlchemy needs its own driver scheme back.
$env:DATABASE_URL = $TargetUrl -replace '^postgresql://', 'postgresql+psycopg://'
try {
    Push-Location $backend
    & $python manage.py init-db
    if ($LASTEXITCODE -ne 0) { throw "init-db failed on the target" }
} finally {
    Pop-Location
    if ($null -eq $prevUrl) { Remove-Item Env:\DATABASE_URL -ErrorAction SilentlyContinue }
    else { $env:DATABASE_URL = $prevUrl }
}

# ------------------------------------------------ 2. refuse to clobber ---
Write-Host "`n== 2/4  Checking the target is empty ==" -ForegroundColor Cyan
$counts = & $psql $TargetUrl -tAc @"
SELECT coalesce(sum(n),0) FROM (
  SELECT (xpath('/row/c/text()',
          query_to_xml(format('SELECT count(*) AS c FROM %I', table_name), false, true, '')))[1]::text::int AS n
  FROM information_schema.tables
  WHERE table_schema='public' AND table_type='BASE TABLE'
) s
"@
if ($LASTEXITCODE -ne 0) { throw "Could not query the target database" }
$existing = [int]($counts.Trim())
if ($existing -gt 0 -and -not $Force) {
    throw "Target already holds $existing row(s). Re-run with -Force to append anyway, or empty it first."
}
Write-Host "target row count: $existing"

# --------------------------------------------------------- 3. copy data ---
Write-Host "`n== 3/4  Copying data ==" -ForegroundColor Cyan
$dumpDir = Join-Path $env:TEMP "retailshop-migrate-$PID"
New-Item -ItemType Directory -Force -Path $dumpDir | Out-Null
try {
    foreach ($t in $TABLES) {
        $file = Join-Path $dumpDir "$t.sql"
        & $pgDump $sourceUrl --data-only --no-owner --no-privileges --table="public.$t" --file=$file
        if ($LASTEXITCODE -ne 0) { throw "pg_dump failed on table '$t'" }

        & $psql $TargetUrl --quiet --set=ON_ERROR_STOP=1 --file=$file
        if ($LASTEXITCODE -ne 0) { throw "restore failed on table '$t'" }

        $rows = (& $psql $TargetUrl -tAc "SELECT count(*) FROM public.$t").Trim()
        Write-Host ("  {0,-18} {1,6} rows" -f $t, $rows)
    }
} finally {
    Remove-Item -Recurse -Force $dumpDir -ErrorAction SilentlyContinue
}

# ----------------------------------------------------- 4. fix sequences ---
# A data-only restore writes explicit id values but leaves every identity
# sequence at 1, so the very next INSERT would collide on the primary key.
Write-Host "`n== 4/4  Resetting id sequences ==" -ForegroundColor Cyan
& $psql $TargetUrl --quiet --set=ON_ERROR_STOP=1 -c @"
DO `$`$
DECLARE r record; seq text; maxid bigint;
BEGIN
  FOR r IN
    SELECT c.relname AS tbl
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
  LOOP
    seq := pg_get_serial_sequence('public.' || quote_ident(r.tbl), 'id');
    IF seq IS NOT NULL THEN
      EXECUTE format('SELECT coalesce(max(id), 0) FROM public.%I', r.tbl) INTO maxid;
      PERFORM setval(seq, GREATEST(maxid, 1), maxid > 0);
      RAISE NOTICE '  % -> %', r.tbl, GREATEST(maxid, 1);
    END IF;
  END LOOP;
END
`$`$;
"@
if ($LASTEXITCODE -ne 0) { throw "sequence reset failed" }

Write-Host "`nMigration complete." -ForegroundColor Green
Write-Host "Verify with:  & '$psql' '<target-url>' -c '\dt'"
