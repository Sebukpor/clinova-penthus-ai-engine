#!/bin/bash
# ============================================
# Clinova Penthus AI Engine - Backup Script
# Production backup script for OCI VM deployment
# ============================================
# This script:
# 1. Backs up PostgreSQL database
# 2. Backs up Redis data (optional)
# 3. Archives backups with timestamp
# 4. Cleans up old backups (retention policy)
# ============================================

set -e

# Configuration
BACKUP_DIR="${BACKUP_DIR:-/var/backups/penthus}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
POSTGRES_CONTAINER="penthus-postgres"
REDIS_CONTAINER="penthus-redis"
DB_NAME="clinova"
DB_USER="penthus"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"

log_info "Starting backup at $(date)"
log_info "Backup directory: $BACKUP_DIR"

# Backup PostgreSQL
log_info "Backing up PostgreSQL database..."
PG_BACKUP_FILE="${BACKUP_DIR}/postgres_${DB_NAME}_${TIMESTAMP}.sql.gz"

docker exec "$POSTGRES_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" | gzip > "$PG_BACKUP_FILE"

if [ -f "$PG_BACKUP_FILE" ]; then
    PG_SIZE=$(du -h "$PG_BACKUP_FILE" | cut -f1)
    log_success "PostgreSQL backup completed: $PG_BACKUP_FILE ($PG_SIZE)"
else
    log_error "PostgreSQL backup failed"
    exit 1
fi

# Backup Redis (optional - RDB snapshot)
log_info "Backing up Redis data..."
REDIS_BACKUP_FILE="${BACKUP_DIR}/redis_${TIMESTAMP}.rdb"

# Trigger BGSAVE and copy the RDB file
docker exec "$REDIS_CONTAINER" redis-cli BGSAVE || true
sleep 5

# Copy RDB file if it exists
if docker exec "$REDIS_CONTAINER" test -f /data/dump.rdb; then
    docker cp "$REDIS_CONTAINER":/data/dump.rdb "$REDIS_BACKUP_FILE"
    REDIS_SIZE=$(du -h "$REDIS_BACKUP_FILE" | cut -f1)
    log_success "Redis backup completed: $REDIS_BACKUP_FILE ($REDIS_SIZE)"
else
    log_warning "Redis RDB file not found, skipping Redis backup"
fi

# Cleanup old backups
log_info "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.rdb" -mtime +$RETENTION_DAYS -delete
CLEANED_COUNT=$(find "$BACKUP_DIR" -type f -mtime -$RETENTION_DAYS | wc -l)
log_success "Cleanup completed. Current backup count: $CLEANED_COUNT"

# List current backups
log_info "Current backups:"
ls -lh "$BACKUP_DIR"

log_success "Backup completed successfully at $(date)"

# Optional: Upload to OCI Object Storage (uncomment and configure if needed)
# log_info "Uploading backups to OCI Object Storage..."
# oci os object put --bucket-name penthus-backups --file "$PG_BACKUP_FILE" --name "postgres_${TIMESTAMP}.sql.gz"
# oci os object put --bucket-name penthus-backups --file "$REDIS_BACKUP_FILE" --name "redis_${TIMESTAMP}.rdb"

exit 0
