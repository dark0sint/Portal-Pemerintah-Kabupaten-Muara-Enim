#!/bin/sh
# Cadangan harian. Pasang di cron: 0 2 * * * /srv/portal-muaraenim/deploy/backup.sh
set -e
D=/srv/portal-muaraenim; OUT=/var/backups/portal-muaraenim; mkdir -p "$OUT"
S=$(date +%Y%m%d)
python3 -c "import sqlite3;s=sqlite3.connect('$D/instance/portal.db');s.backup(sqlite3.connect('$OUT/portal-$S.db'))"
tar czf "$OUT/uploads-$S.tgz" -C "$D/instance" uploads
chmod 600 "$OUT"/*
find "$OUT" -type f -mtime +30 -delete
