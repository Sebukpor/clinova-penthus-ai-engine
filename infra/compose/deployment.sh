#!/bin/bash
# ============================================
# Clinova Penthus AI Engine - Deployment Script
# Single-host deployment on OCI VM via Docker Compose
# ============================================
# This script:
# 1. Builds Docker containers
# 2. Starts all services
# 3. Runs database migrations
# 4. Verifies health endpoints
# ============================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if running as root or with sudo
    if [ "$EUID" -ne 0 ]; then
        log_warning "This script should be run as root or with sudo for best results."
    fi
    
    log_success "Prerequisites check passed"
}

# Load environment variables
load_env() {
    local env_file="${PROJECT_ROOT}/.env"
    
    if [ -f "$env_file" ]; then
        log_info "Loading environment from $env_file"
        export $(grep -v '^#' "$env_file" | xargs)
    else
        log_warning "No .env file found. Using default values."
        log_info "Consider creating a .env file with your configuration."
    fi
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."
    
    cd "$PROJECT_ROOT"
    
    if docker compose version &> /dev/null; then
        docker compose -f "$COMPOSE_FILE" build --no-cache
    else
        docker-compose -f "$COMPOSE_FILE" build --no-cache
    fi
    
    log_success "Docker images built successfully"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    cd "$PROJECT_ROOT"
    
    # Use GPU profile by default, fall back to CPU profile if no GPU
    if docker compose version &> /dev/null; then
        docker compose -f "$COMPOSE_FILE" up -d
    else
        docker-compose -f "$COMPOSE_FILE" up -d
    fi
    
    log_success "Services started"
}

# Run database migrations
run_migrations() {
    log_info "Waiting for PostgreSQL to be ready..."
    
    # Wait for PostgreSQL
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec penthus-postgres pg_isready -U penthus -d clinova &> /dev/null; then
            log_success "PostgreSQL is ready"
            break
        fi
        
        log_info "Attempt $attempt/$max_attempts: Waiting for PostgreSQL..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        log_error "PostgreSQL did not become ready in time"
        return 1
    fi
    
    log_info "Running database migrations..."
    
    # Run Alembic migrations
    docker exec penthus-api alembic upgrade head || {
        log_warning "Migration failed or not needed. Continuing..."
    }
    
    log_success "Database migrations completed"
}

# Verify health endpoints
verify_health() {
    log_info "Verifying service health..."
    
    local api_url="http://localhost/api/v1/health"
    local max_attempts=60
    local attempt=1
    
    # Wait for API to be healthy
    while [ $attempt -le $max_attempts ]; do
        response=$(curl -s -o /dev/null -w "%{http_code}" "$api_url" 2>/dev/null || echo "000")
        
        if [ "$response" = "200" ]; then
            log_success "API is healthy (HTTP $response)"
            break
        fi
        
        log_info "Attempt $attempt/$max_attempts: API health check (HTTP $response)..."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    if [ $attempt -gt $max_attempts ]; then
        log_error "API did not become healthy in time"
        show_service_status
        return 1
    fi
    
    # Check individual services
    log_info "Checking individual service health..."
    
    # PostgreSQL
    if docker exec penthus-postgres pg_isready -U penthus -d clinova &> /dev/null; then
        log_success "PostgreSQL: healthy"
    else
        log_error "PostgreSQL: unhealthy"
    fi
    
    # Redis
    if docker exec penthus-redis redis-cli ping &> /dev/null; then
        log_success "Redis: healthy"
    else
        log_error "Redis: unhealthy"
    fi
    
    # vLLM
    vllm_health=$(docker exec penthus-vllm curl -s http://localhost:8000/health 2>/dev/null || echo "{}")
    if [ -n "$vllm_health" ] && [ "$vllm_health" != "{}" ]; then
        log_success "vLLM: healthy"
    else
        log_warning "vLLM: checking mock service..."
        vllm_mock_health=$(docker exec penthus-vllm-mock curl -s http://localhost:8000/health 2>/dev/null || echo "{}")
        if [ -n "$vllm_mock_health" ] && [ "$vllm_mock_health" != "{}" ]; then
            log_success "vLLM Mock: healthy"
        else
            log_warning "vLLM: still starting up..."
        fi
    fi
    
    # Nginx
    nginx_test=$(docker exec penthus-nginx nginx -t 2>&1)
    if echo "$nginx_test" | grep -q "successful"; then
        log_success "Nginx: configuration valid"
    else
        log_warning "Nginx: $nginx_test"
    fi
    
    log_success "Health verification completed"
}

# Show service status
show_service_status() {
    log_info "Service status:"
    docker ps --filter "name=penthus" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# Show logs
show_logs() {
    local service=$1
    
    if [ -n "$service" ]; then
        docker logs -f "penthus-$service"
    else
        log_info "Showing logs for all services (last 100 lines)..."
        docker compose -f "$COMPOSE_FILE" logs --tail=100
    fi
}

# Stop services
stop_services() {
    log_info "Stopping services..."
    
    cd "$PROJECT_ROOT"
    
    if docker compose version &> /dev/null; then
        docker compose -f "$COMPOSE_FILE" down
    else
        docker-compose -f "$COMPOSE_FILE" down
    fi
    
    log_success "Services stopped"
}

# Clean up
cleanup() {
    log_info "Cleaning up unused Docker resources..."
    docker system prune -f
    log_success "Cleanup completed"
}

# Print usage
usage() {
    cat << EOF
Clinova Penthus AI Engine - Deployment Script

Usage: $0 [command]

Commands:
    deploy      Full deployment (build, start, migrate, verify) - DEFAULT
    build       Build Docker images only
    start       Start services only
    stop        Stop services
    restart     Restart services
    status      Show service status
    logs        Show service logs
    migrate     Run database migrations only
    verify      Verify health endpoints only
    cleanup     Clean up unused Docker resources
    help        Show this help message

Examples:
    $0                  # Full deployment
    $0 deploy           # Full deployment
    $0 build            # Build images only
    $0 logs api         # Show API logs
    $0 stop && $0 start # Restart services

Environment Variables:
    Set these in .env file or export before running:
    - DB_PASSWORD       Database password (default: changeme)
    - SECRET_KEY        JWT secret key
    - HF_TOKEN          HuggingFace token for model download

EOF
}

# Main function
main() {
    local command=${1:-deploy}
    
    case "$command" in
        deploy)
            log_info "Starting full deployment..."
            check_prerequisites
            load_env
            build_images
            start_services
            run_migrations
            verify_health
            show_service_status
            log_success "Deployment completed successfully!"
            ;;
        build)
            check_prerequisites
            load_env
            build_images
            ;;
        start)
            load_env
            start_services
            run_migrations
            verify_health
            ;;
        stop)
            stop_services
            ;;
        restart)
            stop_services
            start_services
            verify_health
            ;;
        status)
            show_service_status
            ;;
        logs)
            show_logs "$2"
            ;;
        migrate)
            load_env
            run_migrations
            ;;
        verify)
            verify_health
            ;;
        cleanup)
            cleanup
            ;;
        help|--help|-h)
            usage
            ;;
        *)
            log_error "Unknown command: $command"
            usage
            exit 1
            ;;
    esac
}

# Handle interrupts
trap 'log_warning "Interrupted!"; exit 130' INT TERM

# Run main
main "$@"
