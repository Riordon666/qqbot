# Restore procedure

Backups are local, mode `600`, and may contain `.env`, OneBot credentials, NapCat configuration, and optionally QQ login state. Treat every archive as a credential. Never upload it to a public issue, repository, or paste service.

## 1. Verify before touching the running service

```bash
cd /path/to/qqbot
project_root=$(pwd -P)
archive="$project_root/backups/qqbot-YYYYMMDD-HHMMSS-NNNNNNNNN.tar.gz"
sha256sum -c "$archive.sha256"
review_dir=$(mktemp -d "$project_root/backups/.restore-review.XXXXXX")
chmod 700 "$review_dir"
tar -xzf "$archive" -C "$review_dir"
find "$review_dir" -maxdepth 3 -type f -printf '%m %p\n'
printf 'Review directory: %s\n' "$review_dir"
```

Read `$review_dir/MANIFEST.txt` and confirm the archive date, Git commit, whether QQ state is included, whether `napcat_quiesced=true`, and the expected image references. Keep this terminal open so `review_dir` remains available.

## 2. Stop writes

```bash
cd "$project_root"
sudo docker compose down
```

Do not restore SQLite while NoneBot is writing to it.

## 3. Preserve the current state

Move each current item into a new mode-700 preservation directory before copying restored data. The following is deliberately reversible and never deletes the pre-restore state:

```bash
cd "$project_root"
[ -n "$review_dir" ] && [ -d "$review_dir" ] || {
  echo "review_dir is missing; repeat verification in this shell" >&2
  exit 1
}

restore_qq=false
if grep -qx 'qq_state_included=true' "$review_dir/MANIFEST.txt"; then
  if ! grep -qx 'napcat_quiesced=true' "$review_dir/MANIFEST.txt" || [ ! -f "$review_dir/napcat/QQ_STATE_WARNING.txt" ] || [ ! -d "$review_dir/napcat/qq" ]; then
    echo "QQ state markers are incomplete; refusing to replace current QQ state" >&2
    exit 1
  fi
  restore_qq=true
fi

if [ -f "$review_dir/data/bot.db" ]; then
  python3 - "$review_dir/data/bot.db" <<'PY'
import sqlite3
import sys

connection = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
try:
    result = connection.execute("PRAGMA quick_check").fetchone()
finally:
    connection.close()
if result is None or result[0] != "ok":
    raise SystemExit(f"SQLite quick_check failed: {result}")
PY
fi

timestamp=$(date +%Y%m%d-%H%M%S)
pre_restore="$project_root/backups/pre-restore-$timestamp"
mkdir -m 700 "$pre_restore"

if [ -f "$review_dir/data/bot.db" ]; then
  mkdir -p data/nonebot
  for database_file in bot.db bot.db-wal bot.db-shm; do
    [ ! -e "data/nonebot/$database_file" ] || mv "data/nonebot/$database_file" "$pre_restore/$database_file"
  done
  cp -a "$review_dir/data/bot.db" data/nonebot/bot.db
  chmod 600 data/nonebot/bot.db
fi

if [ -f "$review_dir/.env" ]; then
  [ ! -e .env ] || mv .env "$pre_restore/.env"
  cp -a "$review_dir/.env" .env
fi

if [ -d "$review_dir/napcat/config" ]; then
  [ ! -e napcat/config ] || mv napcat/config "$pre_restore/napcat-config"
  cp -a "$review_dir/napcat/config" napcat/config
fi

if "$restore_qq"; then
  [ ! -e napcat/qq ] || mv napcat/qq "$pre_restore/napcat-qq"
  cp -a "$review_dir/napcat/qq" napcat/qq
fi

chmod 600 .env
chmod 700 backups napcat napcat/config napcat/qq "$pre_restore"
mapfile -t runtime_ids < <(python3 - <<'PY'
from pathlib import Path

values = {}
for line in Path('.env').read_text(encoding='utf-8').splitlines():
    key, separator, value = line.partition('=')
    if separator:
        values[key.strip()] = value.strip().strip('\"').strip("'")
for key in ('APP_UID', 'APP_GID', 'NAPCAT_UID', 'NAPCAT_GID'):
    value = values.get(key, '1000')
    if not value.isdecimal() or int(value) <= 0:
        raise SystemExit(f'Invalid runtime ownership setting: {key}')
    print(value)
PY
)
[ "${#runtime_ids[@]}" -eq 4 ] || { echo 'Cannot determine runtime ownership' >&2; exit 1; }
sudo chown -R "${runtime_ids[0]}:${runtime_ids[1]}" data/nonebot
sudo chown -R "${runtime_ids[2]}:${runtime_ids[3]}" napcat/config napcat/qq
printf 'Pre-restore state retained at: %s\n' "$pre_restore"
```

`qqbot.git.bundle` can recreate the source repository if the working tree is lost. Restore the source commit and Compose version listed in `MANIFEST.txt` when reverting a code/schema change; the commands above restore runtime data only. Preserve current source edits before switching versions, then rebuild the matching NoneBot image. An image-only automatic rollback does not undo a database migration or bind-mounted Prompt/Skill edits. Do not remove `pre_restore` or `review_dir` until all validation passes.

## 4. Start and validate

```bash
cd "$project_root"
sudo docker compose config --quiet
sudo docker compose up -d
./scripts/status.sh
./scripts/logs.sh all --tail 200
```

Then verify QQ login, Reverse WebSocket connection, `ping`, `help`, administrator permissions, and host listening ports. Keep the preserved pre-restore state until all checks pass.
