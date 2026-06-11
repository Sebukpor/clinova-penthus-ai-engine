# SERVER-PREPARATION.md

# Clinova Penthus AI Engine - Server Preparation Guide

## Overview

This guide prepares an OCI Compute VM for deploying the Clinova Penthus AI Engine. The target VM may have previously hosted a standalone OCR service with Apache, old containers, and NVIDIA driver remnants.

**Target Environment:** Single OCI Compute Instance (GPU or CPU)
**Deployment Method:** Docker Compose
**No Kubernetes, Terraform, or Helm required**

---

## Prerequisites

- SSH access to the OCI VM as `opc` user
- Sudo privileges on the VM
- Network access to download Docker images
- Sufficient disk space (minimum 50GB recommended)

---

## Step 1: Initial Connection and Assessment

```bash
# SSH into the VM
ssh -i ~/.ssh/id_rsa opc@<VM_PUBLIC_IP>

# Check current user and privileges
whoami
sudo whoami  # Should return 'root'

# Check OS version
cat /etc/os-release

# Check available disk space
df -h

# Check memory
free -h

# Check CPU information
lscpu | grep -E "Model name|CPU\(s\)"
```

---

## Step 2: Clean Up Previous OCR Installation

### 2.1 Stop and Remove Old Containers

```bash
# List all running containers
docker ps

# List all containers (including stopped)
docker ps -a

# Stop all running containers
docker stop $(docker ps -q)

# Remove all containers
docker rm $(docker ps -aq)

# Verify no containers remain
docker ps -a  # Should be empty
```

### 2.2 Remove Old Docker Images

```bash
# List all images
docker images

# Remove all images (force if needed)
docker rmi $(docker images -q) --force

# Or selectively remove OCR-related images
docker images | grep -i ocr | awk '{print $3}' | xargs docker rmi --force
docker images | grep -i apache | awk '{print $3}' | xargs docker rmi --force

# Verify cleanup
docker images  # Should be empty or minimal
```

### 2.3 Remove Old Volumes

```bash
# List all volumes
docker volume ls

# Remove all volumes (WARNING: This deletes all data)
docker volume prune -f

# Or selectively remove OCR-related volumes
docker volume ls | grep -i ocr | awk '{print $2}' | xargs -I {} docker volume rm {}

# Verify cleanup
docker volume ls
```

### 2.4 Clean Docker System

```bash
# Remove unused data (images, containers, volumes, networks)
docker system prune -a --volumes -f

# Check disk space reclaimed
df -h
```

---

## Step 3: Remove Apache Configuration

```bash
# Check if Apache is installed
which httpd || which apache2

# Check Apache status
sudo systemctl status httpd 2>/dev/null || sudo systemctl status apache2 2>/dev/null || echo "Apache not found"

# Stop Apache if running
sudo systemctl stop httpd 2>/dev/null || sudo systemctl stop apache2 2>/dev/null || true

# Disable Apache
sudo systemctl disable httpd 2>/dev/null || sudo systemctl disable apache2 2>/dev/null || true

# Remove Apache packages (Oracle Linux)
sudo dnf remove -y httpd httpd-tools 2>/dev/null || true

# Remove Apache packages (Ubuntu/Debian)
sudo apt-get remove -y apache2 apache2-utils 2>/dev/null || true

# Remove Apache configuration directories
sudo rm -rf /etc/httpd 2>/dev/null || true
sudo rm -rf /etc/apache2 2>/dev/null || true
sudo rm -rf /var/www/html 2>/dev/null || true

# Verify port 80 is free
sudo ss -tlnp | grep :80 || echo "Port 80 is free"
```

---

## Step 4: Verify NVIDIA Drivers (GPU Instances Only)

Skip this section for CPU-only instances.

```bash
# Check if NVIDIA drivers are installed
nvidia-smi

# Expected output should show GPU information:
# +-----------------------------------------------------------------------------+
# | NVIDIA-SMI ...   Driver Version: ...   CUDA Version: ...                    |
# |-------------------------------+----------------------+----------------------|
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# +-------------------------------+----------------------+----------------------+

# If nvidia-smi fails, install NVIDIA drivers:
# For Oracle Linux with GPU image:
sudo dnf install -y nvidia-driver-latest-dkms

# Load NVIDIA modules
sudo modprobe nvidia
sudo modprobe nvidia-uvm

# Verify again
nvidia-smi

# Check NVIDIA Container Toolkit
which nvidia-container-cli || echo "NVIDIA Container Toolkit not installed"

# Install NVIDIA Container Toolkit if missing:
# Distribution=$( . /etc/os-release;echo $ID$VERSION_ID )
# curl -s -L https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo | \
#   sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo
# sudo dnf install -y nvidia-container-toolkit
# sudo systemctl restart docker
```

---

## Step 5: Verify Port Availability

```bash
# Check required ports are free
echo "Checking port 80 (HTTP)..."
sudo ss -tlnp | grep :80 && echo "PORT 80 IN USE" || echo "Port 80: FREE"

echo "Checking port 443 (HTTPS)..."
sudo ss -tlnp | grep :443 && echo "PORT 443 IN USE" || echo "Port 443: FREE"

echo "Checking port 22 (SSH)..."
sudo ss -tlnp | grep :22 && echo "Port 22 in use (expected for SSH)" || echo "WARNING: Port 22 not listening"

# Check firewall status
sudo firewall-cmd --list-all 2>/dev/null || sudo ufw status 2>/dev/null || echo "Firewall status unknown"

# Configure firewall if needed (Oracle Linux)
sudo firewall-cmd --permanent --add-service=http 2>/dev/null || true
sudo firewall-cmd --permanent --add-service=https 2>/dev/null || true
sudo firewall-cmd --permanent --add-service=ssh 2>/dev/null || true
sudo firewall-cmd --reload 2>/dev/null || true

# Configure firewall if needed (Ubuntu)
sudo ufw allow 80/tcp 2>/dev/null || true
sudo ufw allow 443/tcp 2>/dev/null || true
sudo ufw allow 22/tcp 2>/dev/null || true
sudo ufw reload 2>/dev/null || true
```

---

## Step 6: Install Docker and Docker Compose

```bash
# Check if Docker is already installed
docker --version || echo "Docker not installed"

# Install Docker (if not present)
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sudo sh /tmp/get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Enable and start Docker
sudo systemctl enable docker
sudo systemctl start docker
sudo systemctl status docker

# Verify Docker installation
docker --version
docker info

# Install Docker Compose plugin
sudo apt-get update && sudo apt-get install -y docker-compose-plugin 2>/dev/null || \
sudo dnf install -y docker-compose-plugin 2>/dev/null || true

# Verify Docker Compose
docker compose version
```

---

## Step 7: Prepare PostgreSQL and Redis Directories

```bash
# Create data directories
sudo mkdir -p /var/lib/penthus/postgres
sudo mkdir -p /var/lib/penthus/redis
sudo mkdir -p /var/lib/penthus/vllm
sudo mkdir -p /var/log/penthus
sudo mkdir -p /var/backups/penthus

# Set ownership
sudo chown -R 999:999 /var/lib/penthus/postgres 2>/dev/null || true
sudo chown -R 1000:1000 /var/lib/penthus/redis 2>/dev/null || true
sudo chown -R $USER:$USER /var/lib/penthus/vllm
sudo chown -R $USER:$USER /var/log/penthus
sudo chown -R $USER:$USER /var/backups/penthus

# Set permissions
sudo chmod 700 /var/lib/penthus/postgres
sudo chmod 700 /var/lib/penthus/redis
```

---

## Step 8: Prepare SSL Certificates (Optional but Recommended)

```bash
# Create SSL directory
mkdir -p ~/penthus/ssl

# Option A: Use Let's Encrypt (requires domain)
# Install certbot
sudo dnf install -y certbot 2>/dev/null || sudo apt-get install -y certbot 2>/dev/null

# Get certificate (replace with your domain)
# sudo certbot certonly --standalone -d your-domain.com

# Copy certificates
# sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ~/penthus/ssl/
# sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ~/penthus/ssl/

# Option B: Generate self-signed certificate (for testing)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ~/penthus/ssl/privkey.pem \
  -out ~/penthus/ssl/fullchain.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# Set permissions
chmod 600 ~/penthus/ssl/*.pem

# Verify SSL files exist
ls -la ~/penthus/ssl/
```

---

## Step 9: Clone Repository and Configure Environment

```bash
# Navigate to home directory
cd ~

# Clone the repository
git clone <YOUR_REPOSITORY_URL> penthus
cd ~/penthus

# Or copy via SCP from local machine:
# scp -r /local/path/to/repo opc@<VM_IP>:~/penthus

# Create .env file from template
cp .env.prod.example .env

# Edit environment variables (use vim, nano, or vi)
nano .env

# Required changes:
# - SECRET_KEY: Generate secure random key
# - DB_PASSWORD: Generate secure password
# - HF_TOKEN: Your HuggingFace token

# Generate secure SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate secure DB_PASSWORD
python3 -c "import secrets; print(secrets.token_urlsafe(16))"
```

---

## Step 10: Final Verification

```bash
# Run comprehensive checks
echo "=== FINAL VERIFICATION ==="

echo ""
echo "1. Docker Status:"
docker --version
docker info | grep -E "Storage Driver|Operating System"

echo ""
echo "2. Docker Compose:"
docker compose version

echo ""
echo "3. Disk Space:"
df -h /

echo ""
echo "4. Memory:"
free -h

echo ""
echo "5. NVIDIA (GPU only):"
nvidia-smi 2>/dev/null || echo "N/A (CPU instance)"

echo ""
echo "6. Ports Available:"
sudo ss -tlnp | grep -E ":80|:443" || echo "Ports 80/443 free"

echo ""
echo "7. Repository Structure:"
ls -la ~/penthus/infra/compose/

echo ""
echo "=== PREPARATION COMPLETE ==="
```

---

## Troubleshooting

### Docker Permission Denied

```bash
# Add user to docker group and re-login
sudo usermod -aG docker $USER
newgrp docker
```

### Port Already in Use

```bash
# Find process using port
sudo ss -tlnp | grep :80

# Kill process if safe
sudo kill -9 <PID>
```

### NVIDIA Driver Issues

```bash
# Reinstall NVIDIA container toolkit
sudo dnf reinstall -y nvidia-container-toolkit 2>/dev/null || true
sudo systemctl restart docker
```

### Insufficient Disk Space

```bash
# Clean Docker
docker system prune -a --volumes -f

# Remove old kernels (Oracle Linux)
sudo dnf remove -y $(dnf repoquery --installonly --latest-limit=-1 -q) 2>/dev/null || true
```

---

## Next Steps

After completing server preparation, proceed to:

1. **DEPLOYMENT-OCI-MVP.md** - Full deployment instructions
2. Run `./infra/compose/deployment.sh deploy`
3. Verify health with `./infra/compose/healthcheck.sh`
4. Configure backup cron job with `./infra/compose/backup.sh`
