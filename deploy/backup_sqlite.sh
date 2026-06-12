#!/usr/bin/env bash
set -e

APP_DIR="/opt/jizhi-growth-system"
BACKUP_DIR="$APP_DIR/backups"
DB_FILE="$APP_DIR/data/marketing.db"

mkdir -p $BACKUP_DIR

if [ -f "$DB_FILE" ]; then
  cp "$DB_FILE" "$BACKUP_DIR/marketing_$(date +%Y%m%d_%H%M%S).db"
  find "$BACKUP_DIR" -name "marketing_*.db" -mtime +14 -delete
  echo "$(date): Backup completed → $BACKUP_DIR"
else
  echo "$(date): Database file not found: $DB_FILE"
fi
