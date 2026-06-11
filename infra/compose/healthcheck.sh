#!/bin/bash
# ============================================
# Clinova Penthus AI Engine - Health Check Script
# Production health verification for OCI VM deployment
# ============================================
# This script:
# 1. Checks container status
# 2. Verifies service health endpoints
# 3. Tests database connectivity
# 4. Tests Redis connectivity
# 5. Reports overall system health
# ============================================

set -e

# Configuration
API_URL="${API_URL:-http://localhost/api/v1}"
POSTGRES_CONTAINER="penthus-postgres"
REDIS_CONTAINER="penthus-redis"
API_CONTAINER="penthus-api"
NGINX_CONTAINER="penthus-nginx"
VLLM_CONTAINER="penthus-vllm"
DB_NAME="clinova"
DB_USER="penthus"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

HEALTH_STATUS=0

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
    HEALTH_STATUS=1
}

echo "============================================"
echo "Clinova Penthus AI Engine - Health Check"
echo "Timestamp: $(date)"
echo "============================================"
echo ""

# Check Docker containers
log_info "Checking container status..."

check_container() {
    local container=$1
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        STATUS=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
        if [ "$STATUS" = "running" ]; then
            log_success "$container: running"
        else
            log_error "$container: $STATUS"
        fi
    else
        log_error "$container: not found"
    fi
}

check_container "$NGINX_CONTAINER"
check_container "$API_CONTAINER"
check_container "$POSTGRES_CONTAINER"
check_container "$REDIS_CONTAINER"
check_container "$VLLM_CONTAINER" || check_container "penthus-vllm-mock"

echo ""

# Check API health endpoint
log_info "Checking API health endpoint..."
API_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "${API_URL}/health" 2>/dev/null || echo "000")
if [ "$API_HEALTH" = "200" ]; then
    log_success "API health: HTTP $API_HEALTH"
else
    log_error "API health: HTTP $API_HEALTH"
fi

# Check API readiness
log_info "Checking API readiness (dependencies)..."
API_READINESS=$(curl -s "${API_URL}/readiness" 2>/dev/null || echo "{}")
if echo "$API_READINESS" | grep -q '"ready":true'; then
    log_success "API readiness: all dependencies ready"
else
    log_warning "API readiness: some dependencies may be unavailable"
    echo "$API_READINESS" | python3 -m json.tool 2>/dev/null || echo "$API_READINESS"
fi

echo ""

# Check PostgreSQL
log_info "Checking PostgreSQL..."
if docker exec "$POSTGRES_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" &>/dev/null; then
    log_success "PostgreSQL: accepting connections"
    
    # Check database size
    DB_SIZE=$(docker exec "$POSTGRES_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" 2>/dev/null | tr -d ' ')
    log_info "Database size: $DB_SIZE"
else
    log_error "PostgreSQL: not accepting connections"
fi

echo ""

# Check Redis
log_info "Checking Redis..."
REDIS_PING=$(docker exec "$REDIS_CONTAINER" redis-cli ping 2>/dev/null || echo "FAILED")
if [ "$REDIS_PING" = "PONG" ]; then
    log_success "Redis: responding to PING"
    
    # Check memory usage
    REDIS_MEMORY=$(docker exec "$REDIS_CONTAINER" redis-cli INFO memory 2>/dev/null | grep "used_memory_human" | cut -d: -f2 | tr -d '\r')
    log_info "Redis memory: $REDIS_MEMORY"
else
    log_error "Redis: not responding ($REDIS_PING)"
fi

echo ""

# Check vLLM
log_info "Checking vLLM..."
VLLM_HEALTH=$(docker exec "$VLLM_CONTAINER" curl -s http://localhost:8000/health 2>/dev/null || echo "{}")
if [ -n "$VLLM_HEALTH" ] && [ "$VLLM_HEALTH" != "{}" ]; then
    log_success "vLLM: healthy"
else
    # Try mock vLLM
    VLLM_MOCK_HEALTH=$(docker exec penthus-vllm-mock curl -s http://localhost:8000/health 2>/dev/null || echo "{}")
    if [ -n "$VLLM_MOCK_HEALTH" ] && [ "$VLLM_MOCK_HEALTH" != "{}" ]; then
        log_success "vLLM Mock: healthy"
    else
        log_warning "vLLM: still starting or unavailable"
    fi
fi

echo ""

# Check disk space
log_info "Checking disk space..."
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}')
DISK_AVAIL=$(df -h / | tail -1 | awk '{print $4}')
if [ "${DISK_USAGE%\%}" -lt 80 ]; then
    log_success "Disk usage: $DISK_USAGE (available: $DISK_AVAIL)"
elif [ "${DISK_USAGE%\%}" -lt 90 ]; then
    log_warning "Disk usage: $DISK_USAGE (available: $DISK_AVAIL)"
else
    log_error "Disk usage: $DISK_USAGE (available: $DISK_AVAIL)"
fi

echo ""

# Check Docker resources
log_info "Checking Docker resources..."
CONTAINER_COUNT=$(docker ps -q | wc -l)
IMAGE_COUNT=$(docker images -q | wc -l)
log_info "Running containers: $CONTAINER_COUNT"
log_info "Docker images: $IMAGE_COUNT"

echo ""
echo "============================================"
if [ $HEALTH_STATUS -eq 0 ]; then
    echo -e "${GREEN}Overall Status: HEALTHY${NC}"
else
    echo -e "${RED}Overall Status: UNHEALTHY${NC}"
fi
echo "============================================"

exit $HEALTH_STATUS
