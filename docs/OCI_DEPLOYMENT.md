# Clinova Penthus AI Engine - OCI Deployment Guide

## Overview

This guide describes how to deploy the Clinova Penthus AI Engine on Oracle Cloud Infrastructure (OCI) using Docker Compose on a single VM instance. No Kubernetes or Terraform required.

## Architecture

```
Internet
    |
    v
OCI Load Balancer (optional)
    |
    v
OCI Compute VM (GPU or CPU)
    |
    +-- Nginx (reverse proxy)
    |       |
    |       v
    |   FastAPI Application
    |       |
    |       +-- PostgreSQL (clinical data)
    |       +-- Redis (caching)
    |       +-- vLLM (model inference)
```

## Prerequisites

1. **OCI Account** with appropriate permissions
2. **OCI CLI** installed and configured on your local machine
3. **SSH key pair** for VM access

## Step 1: Create OCI Compute Instance

### Option A: GPU Instance (Recommended for Production)

```bash
# Create GPU-enabled VM (BM.GPU.A10.1 shape)
oci compute instance launch \
  --compartment-id <your-compartment-ocid> \
  --availability-domain <your-ad> \
  --shape BM.GPU.A10.1 \
  --display-name penthus-ai-vm \
  --image-id <gpu-enabled-oracle-linux-image-ocid> \
  --ssh-authorized-keys-file ~/.ssh/id_rsa.pub \
  --subnet-id <your-subnet-ocid> \
  --assign-public-ip true \
  --metadata '{"ssh_authorized_keys": "'"$(cat ~/.ssh/id_rsa.pub)"'" }'
```

### Option B: CPU Instance (Development/Testing)

```bash
# Create CPU-only VM (VM.Standard.E4.Flex)
oci compute instance launch \
  --compartment-id <your-compartment-ocid> \
  --availability-domain <your-ad> \
  --shape VM.Standard.E4.Flex \
  --shape-config '{"ocpus":4,"memory_in_gbs":16}' \
  --display-name penthus-ai-vm-cpu \
  --image-id <oracle-linux-9-image-ocid> \
  --ssh-authorized-keys-file ~/.ssh/id_rsa.pub \
  --subnet-id <your-subnet-ocid> \
  --assign-public-ip true
```

### Configure Security List

Allow required ports:

```bash
# Update security list to allow HTTP, HTTPS, SSH
oci network security-rule create \
  --security-list-id <your-security-list-ocid> \
  --direction INGRESS \
  --protocol all \
  --source-type CIDR \
  --source "0.0.0.0/0" \
  --description "Allow HTTP/HTTPS/SSH"
```

Or manually in OCI Console:
- Port 22 (SSH)
- Port 80 (HTTP)
- Port 443 (HTTPS)

## Step 2: Connect to VM

```bash
# Get public IP
PUBLIC_IP=$(oci compute instance get \
  --instance-id <your-instance-ocid> \
  --query 'data."public-ip"' \
  --raw-output)

# SSH into VM
ssh -i ~/.ssh/id_rsa opc@$PUBLIC_IP
```

## Step 3: Install Docker on VM

```bash
# Update system
sudo dnf update -y

# Install Docker
sudo dnf install -y docker

# Start and enable Docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker opc

# Install Docker Compose plugin
sudo dnf install -y docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

## Step 4: Clone Repository

```bash
# Clone repository
git clone <your-repo-url> /home/opc/penthus
cd /home/opc/penthus

# Set ownership
sudo chown -R opc:opc /home/opc/penthus
```

## Step 5: Configure Environment

```bash
cd /home/opc/penthus

# Copy environment file
cp .env.example .env

# Edit with your settings
vi .env
```

Required changes in `.env`:

```bash
# Generate secure secret key
SECRET_KEY=$(openssl rand -hex 32)

# Set database password
DB_PASSWORD=<strong-password>

# HuggingFace token (if needed for model download)
HF_TOKEN=<your-hf-token>
```

## Step 6: Deploy with Docker Compose

```bash
cd /home/opc/penthus/infra/compose

# Full deployment
sudo ./deployment.sh deploy

# Or step by step:
# Build images
docker compose build

# Start services
docker compose up -d

# Run migrations
docker exec penthus-api alembic upgrade head

# Check status
docker compose ps
```

## Step 7: Verify Deployment

```bash
# Check API health
curl http://localhost/api/v1/health

# Expected response:
# {"status":"healthy","service":"penthus-ai-engine"}

# Check individual services
docker compose ps
```

## Step 8: Configure SSL (Optional but Recommended)

### Using Let's Encrypt

```bash
# Install Certbot
sudo dnf install -y certbot python3-certbot-nginx

# Get certificate (requires domain pointing to VM)
sudo certbot --nginx -d your-domain.com

# Update nginx.conf to use certificates
# Uncomment HTTPS server block in nginx.conf
```

## Cost Optimization

### Monthly Cost Estimate (US East region)

| Resource | Shape | Monthly Cost |
|----------|-------|--------------|
| GPU VM | BM.GPU.A10.1 | ~$3,000 |
| CPU VM | VM.Standard.E4.Flex | ~$100 |
| Boot Volume | 200GB | ~$10 |
| **Total (CPU)** | | **~$110/month** |
| **Total (GPU)** | | **~$3,010/month** |

### Cost-Saving Tips

1. **Use CPU instance for development/testing** - vLLM mock service works without GPU
2. **Stop instance when not in use** - Save compute costs
3. **Use Always Free resources** where possible
4. **Right-size boot volume** - 50GB minimum for application

## Monitoring

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f vllm
```

### Health Checks

```bash
# API health
curl http://localhost/api/v1/health

# PostgreSQL health
docker exec penthus-postgres pg_isready -U penthus

# Redis health
docker exec penthus-redis redis-cli ping

# vLLM health
curl http://localhost:8001/health
```

## Backup Strategy

### Database Backup

```bash
# Create backup script
cat > /home/opc/backup-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/opc/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

docker exec penthus-postgres pg_dump -U penthus clinova > $BACKUP_DIR/clinova_$DATE.sql

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
EOF

chmod +x /home/opc/backup-db.sh

# Add to crontab (daily at 2 AM)
echo "0 2 * * * /home/opc/backup-db.sh" | crontab -
```

### Volume Backup

```bash
# Backup Docker volumes
docker run --rm \
  -v penthus_postgres_data:/data:ro \
  -v /home/opc/backups:/backup \
  alpine tar czf /backup/postgres_data_$(date +%Y%m%d).tar.gz -C /data .
```

## Troubleshooting

### Common Issues

1. **Container won't start**
   ```bash
   docker compose logs <service-name>
   ```

2. **Database connection failed**
   ```bash
   docker exec penthus-postgres pg_isready -U penthus
   ```

3. **vLLM out of memory**
   - Reduce `GPU_MEMORY_UTILIZATION` in docker-compose.yml
   - Use smaller model or CPU mock service

4. **Port already in use**
   ```bash
   sudo netstat -tulpn | grep :8000
   ```

### Restart Services

```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart api
```

## Upgrading

```bash
cd /home/opc/penthus

# Pull latest code
git pull

# Rebuild and redeploy
cd infra/compose
sudo ./deployment.sh deploy
```

## Security Considerations

1. **Change default passwords** in `.env`
2. **Enable firewall** (firewalld)
3. **Regular security updates**: `sudo dnf update -y`
4. **Use private networking** for database/Redis
5. **Enable SSL/TLS** for production
6. **Rotate secrets regularly**
7. **Monitor access logs**

## Support

For issues:
1. Check logs: `docker compose logs -f`
2. Verify health endpoints
3. Review OCI Console for instance metrics
4. Check Docker resource usage: `docker stats`
