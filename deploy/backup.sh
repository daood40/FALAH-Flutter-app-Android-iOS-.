#!/bin/sh
# نسخةٌ حيّة من قاعدة التطبيق دون إيقاف الخدمة (نسخ SQLite الآمن مع WAL).
# cron مقترح:  0 3 * * *  /opt/falah/deploy/backup.sh /opt/falah/backups
set -eu
DEST="${1:-./backups}"; KEEP="${2:-14}"
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)
DB="${FALAH_APP_DB:-/data/app.db}"
OUT="$DEST/app-$STAMP.db"

# sqlite3 إن وُجد، وإلا فبايثون — كلاهما ينسخ نسخةً متّسقة
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '$OUT'"
else
  python3 -c 'import sqlite3,sys
src=sqlite3.connect("file:%s?mode=ro"%sys.argv[1],uri=True); dst=sqlite3.connect(sys.argv[2])
with dst: src.backup(dst)
src.close(); dst.close()' "$DB" "$OUT"
fi

gzip -f "$OUT"
# يُبقى آخرُ KEEP نسخة ويُحذف ما قبلها
ls -1t "$DEST"/app-*.db.gz 2>/dev/null | tail -n +$((KEEP+1)) | xargs -r rm --
echo "نسخة: $OUT.gz"
