# Complete Guide: Deploying Clinova Penthus AI Engine to Oracle Cloud Infrastructure (OCI)

This comprehensive guide walks you through deploying the Clinova Penthus Clinical AI Engine to Oracle Cloud Infrastructure (OCI) from scratch. This guide assumes you are new to OCI and provides detailed, step-by-step instructions.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [OCI Account Setup](#2-oci-account-setup)
3. [OCI CLI and Configuration](#3-oci-cli-and-configuration)
4. [Required OCI Services Overview](#4-required-oci-services-overview)
5. [Step 1: Set Up Identity and Access Management (IAM)](#5-step-1-set-up-identity-and-access-management-iam)
6. [Step 2: Configure Terraform](#6-step-2-configure-terraform)
7. [Step 3: Deploy Infrastructure with Terraform](#7-step-3-deploy-infrastructure-with-terraform)
8. [Step 4: Build and Push Docker Images](#8-step-4-build-and-push-docker-images)
9. [Step 5: Configure Kubernetes (kubectl)](#9-step-5-configure-kubernetes-kubectl)
10. [Step 6: Prepare Kubernetes Secrets](#10-step-6-prepare-kubernetes-secrets)
11. [Step 7: Deploy Applications to OKE](#11-step-7-deploy-applications-to-oke)
12. [Step 8: Configure Load Balancer and DNS](#12-step-8-configure-load-balancer-and-dns)
13. [Step 9: Verify Deployment](#13-step-9-verify-deployment)
14. [Step 10: Set Up Monitoring and Alerts](#14-step-10-set-up-monitoring-and-alerts)
15. [Troubleshooting](#15-troubleshooting)
16. [Cost Optimization Tips](#16-cost-optimization-tips)

---

## 1. Prerequisites

### Local Machine Requirements

Before starting, ensure you have the following installed on your local machine:

| Tool | Version | Purpose | Download Link |
|------|---------|---------|---------------|
| **OCI CLI** | Latest | Interact with OCI services | [Download](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/cliconcepts.htm) |
| **Terraform** | >= 1.5.0 | Infrastructure as Code | [Download](https://www.terraform.io/downloads) |
| **kubectl** | Latest | Kubernetes management | [Download](https://kubernetes.io/docs/tasks/tools/) |
| **Docker** | Latest | Container building | [Download](https://www.docker.com/get-started) |
| **Python** | 3.12+ | Application development | [Download](https://www.python.org/downloads) |
| **Git** | Latest | Version control | [Download](https://git-scm.com/downloads) |

### Verify Installations

```bash
# Check OCI CLI
oci --version

# Check Terraform
terraform version

# Check kubectl
kubectl version --client

# Check Docker
docker --version

# Check Python
python3 --version
```

### Required Accounts and Access

- **Oracle Cloud Infrastructure (OCI) Account**: Free tier or paid account
- **GitHub Account**: To clone the repository
- **Hugging Face Account**: For model access (if using private models)
- **Domain Name** (optional): For production DNS setup

---

## 2. OCI Account Setup

### 2.1 Create OCI Account

1. Visit [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)
2. Click "Start for free" and complete registration
3. Verify your email and phone number
4. Log in to the OCI Console at https://cloud.oracle.com

### 2.2 Understand OCI Tenancy Structure

When you log in, note the following:

- **Tenancy**: Your organization's root container (e.g., `mycompany-tenancy`)
- **Compartment**: Logical grouping of resources (we'll create one called `clinova`)
- **Region**: Geographic location (we'll use `us-ashburn-1` as default)
- **Home Region**: Your tenancy's primary region

### 2.3 Create a Compartment

Compartments help organize and isolate resources:

1. Navigate to **Identity & Security** → **Compartments**
2. Click **Create Compartment**
3. Enter details:
   - **Name**: `clinova`
   - **Description**: `Clinova Penthus AI Engine Resources`
   - **Parent Compartment**: Select your root tenancy
4. Click **Create Compartment**
5. **Note the Compartment OCID** (you'll need this for Terraform)

---

## 3. OCI CLI and Configuration

### 3.1 Install OCI CLI

#### macOS
```bash
curl -O https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh
chmod +x install.sh
./install.sh
```

#### Linux
```bash
curl -O https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh
chmod +x install.sh
./install.sh
```

#### Windows (PowerShell)
```powershell
Invoke-WebRequest -Uri https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.ps1 -OutFile install.ps1
.\install.ps1
```

### 3.2 Generate API Signing Key

OCI uses API signing keys for authentication:

```bash
# Create directory for keys
mkdir -p $HOME/.oci
cd $HOME/.oci

# Generate private key (2048-bit RSA)
openssl genrsa -out oci_api_key.pem 2048

# Set proper permissions
chmod 600 oci_api_key.pem

# Generate public key
openssl rsa -pubout -outform PEM -out oci_api_key_public.pem -in oci_api_key.pem
```

### 3.3 Upload Public Key to OCI

1. Log in to OCI Console
2. Navigate to **Identity & Security** → **Users**
3. Click on your username
4. Under **Resources**, click **API Keys**
5. Click **Add API Key**
6. Select **Paste public keys**
7. Open and copy the contents of `oci_api_key_public.pem`:
   ```bash
   cat ~/.oci/oci_api_key_public.pem
   ```
8. Paste the key and click **Add**
9. **Note the Key Fingerprint** displayed (you'll need this)

### 3.4 Configure OCI CLI

```bash
oci setup config
```

You'll be prompted for:

```
Enter user OCID: ocid1.user.oc1..xxxxxx
Enter fingerprint: xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
Enter path to private key: /home/user/.oci/oci_api_key.pem
Enter passphrase for private key (optional): [press Enter if none]
Choose a region [us-ashburn-1]: us-ashburn-1
```

This creates `~/.oci/config` with your credentials.

### 3.5 Verify Configuration

```bash
# Test connection
oci iam compartment list --compartment-id-in-subtree=true

# Get your tenancy OCID
oci iam tenancy get

# Get compartment OCID by name
oci iam compartment list --compartment-id-in-subtree=true --name clinova
```

---

## 4. Required OCI Services Overview

The Clinova Penthus AI Engine uses the following OCI services:

| Service | Purpose | Pricing Tier |
|---------|---------|--------------|
| **OKE (Oracle Kubernetes Engine)** | Container orchestration | ~$0.096/hour per cluster + node costs |
| **Compute (VM Shapes)** | CPU and GPU nodes | VM.Standard.E4.Flex (~$0.17/hr), VM.GPU.A10.1 (~$3.09/hr) |
| **Container Registry (OCIR)** | Docker image storage | Free up to 500GB/month |
| **Object Storage** | Document and model storage | $0.026/GB/month |
| **Vault (KMS)** | Secret management | $1/vault/month + $1/key/month |
| **Load Balancer** | Traffic distribution | ~$20/month + bandwidth |
| **Virtual Cloud Network (VCN)** | Networking | Free |
| **Monitoring & Alarms** | Observability | Free tier available |
| **Logging** | Log aggregation | Free tier available |
| **Block Volumes** | Persistent storage | $0.0417/GB/month |

### Estimated Monthly Cost (Production)

| Component | Configuration | Estimated Cost |
|-----------|--------------|----------------|
| OKE Cluster | 1 cluster | ~$70 |
| CPU Node Pool | 3 × VM.Standard.E4.Flex | ~$370 |
| GPU Node Pool | 2 × VM.GPU.A10.1 | ~$2,225 |
| Load Balancer | 1 × Flexible | ~$20 |
| Block Volumes | 150 GB total | ~$6 |
| Object Storage | 100 GB | ~$3 |
| Vault & Keys | 1 vault, 3 keys | ~$4 |
| **Total** | | **~$2,698/month** |

### Cost-Saving Options

- Use **Always Free** tier for testing (limited GPU availability)
- Reduce GPU nodes to 1 for development
- Use **Auto-scaling** to scale down during low traffic
- Consider **Spot Instances** for non-critical workloads

---

## 5. Step 1: Set Up Identity and Access Management (IAM)

### 5.1 Create Dynamic Group for OKE

Dynamic groups allow OKE pods to access OCI resources without credentials:

1. Navigate to **Identity & Security** → **Dynamic Groups**
2. Click **Create Dynamic Group**
3. Enter details:
   - **Name**: `clinova-oke-pods`
   - **Description**: `OKE pods for Clinova application`
   - **Matching Rules**: 
     ```
     ALL {resource.type = 'instance', resource.compartment.id = 'ocid1.compartment.oc1..xxxxxx'}
     ```
   (Replace with your compartment OCID)
4. Click **Create Dynamic Group**

### 5.2 Create IAM Policies

Policies grant permissions to dynamic groups:

1. Navigate to **Identity & Security** → **Policies**
2. Click **Create Policy**
3. Create the following policies:

#### Policy 1: Object Storage Access
```
Allow dynamic-group clinova-oke-pods to manage objects in compartment clinova
```

#### Policy 2: Vault Access
```
Allow dynamic-group clinova-oke-pods to read secrets in compartment clinova
```

#### Policy 3: KMS Access
```
Allow dynamic-group clinova-oke-pods to use vaults in compartment clinova
```

#### Policy 4: VCN Access
```
Allow dynamic-group clinova-oke-pods to read virtual-network-family in compartment clinova
```

4. Click **Create** after each policy

### 5.3 Create User Group (Optional)

For team members who will manage the deployment:

1. Navigate to **Identity & Security** → **Groups**
2. Click **Create Group**
   - **Name**: `clinova-admins`
   - **Description**: `Administrators for Clinova platform`
3. Add users to the group
4. Create policy:
   ```
   Allow group clinova-admins to manage all-resources in compartment clinova
   ```

---

## 6. Step 2: Configure Terraform

### 6.1 Clone the Repository

```bash
cd ~/projects
git clone <your-repository-url>
cd clinova-penthus-ai-engine
```

### 6.2 Navigate to Terraform Directory

```bash
cd infra/terraform/oci
```

### 6.3 Create terraform.tfvars File

Copy the example file and edit with your values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

If the example file doesn't exist, create it:

```bash
cat > terraform.tfvars << EOF
# OCI Configuration
tenancy_ocid = "ocid1.tenancy.oc1..xxxxxxxxxxxxxx"
region       = "us-ashburn-1"
compartment_ocid = "ocid1.compartment.oc1..xxxxxxxxxxxxxx"
user_ocid    = "ocid1.user.oc1..xxxxxxxxxxxxxx"
fingerprint  = "xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx"
private_key_path = "~/.oci/oci_api_key.pem"

# Environment
environment = "production"

# Secrets (use strong passwords!)
db_password      = "YourSecureDbPassword123!"
hf_token         = "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
app_secret_key   = "your-256-bit-secret-key-here-change-this"
EOF
```

### 6.4 Replace Placeholders

Edit `terraform.tfvars` with your actual values:

| Variable | How to Obtain |
|----------|---------------|
| `tenancy_ocid` | OCI Console → Profile → Tenancy: [your-tenancy-name] |
| `compartment_ocid` | `oci iam compartment list --name clinova --query "data[0].id"` |
| `user_ocid` | OCI Console → Profile → User Settings |
| `fingerprint` | From Step 3.3 (API Key fingerprint) |
| `private_key_path` | Path to your private key (e.g., `~/.oci/oci_api_key.pem`) |
| `db_password` | Create a strong password (16+ characters) |
| `hf_token` | Hugging Face → Settings → Access Tokens |
| `app_secret_key` | Generate random 256-bit string |

### 6.5 Generate Secure Random Values

```bash
# Generate secure database password
openssl rand -base64 32

# Generate application secret key
python3 -c "import secrets; print(secrets.token_hex(32))"

# Or use OpenSSL
openssl rand -hex 32
```

---

## 7. Step 3: Deploy Infrastructure with Terraform

### 7.1 Initialize Terraform

```bash
cd infra/terraform/oci
terraform init
```

Expected output:
```
Terraform has been successfully initialized!
Provider "oci" configured
Backend "s3" initialized (using OCI Object Storage)
```

### 7.2 Validate Configuration

```bash
terraform validate
```

### 7.3 Review Execution Plan

```bash
terraform plan -out=tfplan
```

Review the plan carefully. You should see resources being created:
- VCN with subnets
- OKE Cluster
- Node pools (CPU and GPU)
- Container repositories
- Object storage buckets
- Vault and secrets
- Monitoring alarms

### 7.4 Apply Configuration

```bash
terraform apply tfplan
```

Or directly:
```bash
terraform apply
```

Type `yes` when prompted.

### 7.5 Wait for Provisioning

**Important**: OKE cluster creation takes 15-30 minutes. Monitor progress:

```bash
# In another terminal, watch cluster status
watch -n 30 'oci ce cluster list --compartment-id <your-compartment-ocid> --query "data[0].lifecycle-state"'
```

### 7.6 Note Output Values

After successful deployment, Terraform will display outputs:

```
Outputs:

oke_cluster_id = "ocid1.cluster.oc1.iad.xxxxxx"
container_registry_api = "iad.ocir.io/namespace/clinova/penthus-api"
container_registry_vllm = "iad.ocir.io/namespace/clinova/penthus-vllm"
vault_ocid = "ocid1.vault.oc1.iad.xxxxxx"
vcn_id = "ocid1.vcn.oc1.iad.xxxxxx"
```

**Save these values** – you'll need them for subsequent steps.

---

## 8. Step 4: Build and Push Docker Images

### 8.1 Authenticate Docker to OCI Registry

```bash
# Get auth token
export OCI_NAMESPACE=<your-namespace>
export REGION=us-ashburn-1

docker login -u '<your-tenancy-name>/<your-username>' ${REGION}.ocir.io
```

When prompted for password, enter your **OCI Auth Token**:
1. Go to OCI Console → Profile → User Settings
2. Click **Auth Tokens**
3. Click **Generate Token**
4. Copy the token (shown only once!)

### 8.2 Build API Image

```bash
cd ~/projects/clinova-penthus-ai-engine

# Build API image
docker build -t ${REGION}.ocir.io/${OCI_NAMESPACE}/clinova/penthus-api:1.2.0 \
  -f infra/docker/api.Dockerfile .
```

### 8.3 Build vLLM Image

```bash
# Build vLLM image
docker build -t ${REGION}.ocir.io/${OCI_NAMESPACE}/clinova/penthus-vllm:1.2.0 \
  -f infra/docker/vllm.Dockerfile .
```

### 8.4 Push Images to OCI Registry

```bash
# Push API image
docker push ${REGION}.ocir.io/${OCI_NAMESPACE}/clinova/penthus-api:1.2.0

# Push vLLM image
docker push ${REGION}.ocir.io/${OCI_NAMESPACE}/clinova/penthus-vllm:1.2.0
```

### 8.5 Verify Images in Registry

```bash
# List repositories
oci artifacts container repository list --compartment-id <compartment-ocid>

# List images in repository
oci artifacts container image list --repo-id <repo-ocid>
```

Or check in OCI Console: **Developer Services** → **Container Registry**

---

## 9. Step 5: Configure Kubernetes (kubectl)

### 9.1 Generate Kubeconfig

```bash
# Get cluster OCID from Terraform output
CLUSTER_OCID=$(terraform output -raw oke_cluster_id)

# Generate kubeconfig
oci ce cluster create-kubeconfig \
  --cluster-id $CLUSTER_OCID \
  --file $HOME/.kube/config \
  --region us-ashburn-1 \
  --token-version 2.0.0
```

### 9.2 Verify kubectl Connection

```bash
# Check cluster connection
kubectl cluster-info

# List nodes (may take a few minutes to be ready)
kubectl get nodes

# Expected output:
# NAME             STATUS   ROLES   AGE   VERSION
# 10.0.2.xxx       Ready    worker  5m    v1.29.1
# 10.0.2.yyy       Ready    worker  5m    v1.29.1
# 10.0.2.zzz       Ready    worker  5m    v1.29.1
# 10.0.3.xxx       Ready    worker  5m    v1.29.1  # GPU node
# 10.0.3.yyy       Ready    worker  5m    v1.29.1  # GPU node
```

### 9.3 Install NVIDIA Device Plugin (for GPU nodes)

```bash
kubectl apply -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/main/deployments/static/nvidia-device-plugin.yml
```

Verify GPU nodes are ready:
```bash
kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.capacity.nvidia\.com/gpu
```

---

## 10. Step 6: Prepare Kubernetes Secrets

### 10.1 Create Secrets YAML File

```bash
cd ~/projects/clinova-penthus-ai-engine/infra/k8s
```

Create `secrets.yaml` (DO NOT commit to Git):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: clinova-penthus-secrets
  namespace: clinova
type: Opaque
stringData:
  # Database
  DATABASE_URL: "postgresql+asyncpg://penthus:YourSecureDbPassword123!@postgres.clinova.svc.cluster.local:5432/clinova"
  SYNC_DATABASE_URL: "postgresql://penthus:YourSecureDbPassword123!@postgres.clinova.svc.cluster.local:5432/clinova"
  DB_USER: "penthus"
  DB_PASSWORD: "YourSecureDbPassword123!"

  # Redis
  REDIS_URL: "redis://redis.clinova.svc.cluster.local:6379/0"

  # vLLM / Hugging Face
  VLLM_BASE_URL: "http://penthus-vllm.clinova.svc.cluster.local:8000/v1"
  VLLM_API_KEY: ""
  HF_TOKEN: "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

  # Security
  SECRET_KEY: "your-generated-256-bit-secret-key"
  JWT_ALGORITHM: "HS256"
  ACCESS_TOKEN_EXPIRE_MINUTES: "30"
  API_KEY_HEADER: "X-API-Key"

  # Object Storage (OCI)
  OBJECT_STORAGE_ENDPOINT: "https://objectstorage.us-ashburn-1.oraclecloud.com"
  OBJECT_STORAGE_ACCESS_KEY: "<your-access-key>"
  OBJECT_STORAGE_SECRET_KEY: "<your-secret-key>"
  OBJECT_STORAGE_REGION: "us-ashburn-1"
  OBJECT_STORAGE_BUCKET: "clinova-documents-production"

  # Terminology Gateway
  TERMINOLOGY_GATEWAY_URL: "http://terminology-gateway:8080"

  # FHIR
  FHIR_BASE_URL: "http://fhir-server:8080/fhir"

  # OpenTelemetry
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4317"
```

### 10.2 Alternative: Use OCI Vault Secrets (Recommended for Production)

For better security, retrieve secrets from OCI Vault:

```bash
# Get secret OCIDs from Terraform output
DB_SECRET_OCID=$(terraform output -raw db_secret_ocid)
HF_SECRET_OCID=$(terraform output -raw hf_secret_ocid)
APP_SECRET_OCID=$(terraform output -raw app_secret_ocid)

# Create secret provider class
cat > secret-provider-class.yaml << EOF
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: oci-vault-penthus
  namespace: clinova
spec:
  provider: oracle
  parameters:
    vaultId: "$(terraform output -raw vault_ocid)"
    authType: instance_principal
  secretObjects:
    - secretName: clinova-penthus-secrets
      type: Opaque
      data:
        - objectName: penthus-db-password
          key: DB_PASSWORD
        - objectName: penthus-hf-token
          key: HF_TOKEN
        - objectName: penthus-secret-key
          key: SECRET_KEY
EOF
```

### 10.3 Generate OCI Object Storage Credentials

For accessing object storage from Kubernetes:

1. Navigate to **Identity & Security** → **Customer Secret Keys**
2. Click **Generate Secret Key**
3. Give it a name: `clinova-object-storage`
4. **Copy the Secret Key and Access Key** (shown only once!)

Update your secrets file with these values.

---

## 11. Step 7: Deploy Applications to OKE

### 11.1 Update Kubernetes Manifests

Before deploying, update image references in Kubernetes manifests:

```bash
cd ~/projects/clinova-penthus-ai-engine/infra/k8s

# Replace NAMESPACE placeholder with your actual namespace
sed -i 's/iad.ocir.io\/NAMESPACE/iad.ocir.io\/'"$OCI_NAMESPACE"'/g' api-deployment.yaml
sed -i 's/iad.ocir.io\/NAMESPACE/iad.ocir.io\/'"$OCI_NAMESPACE"'/g' vllm-deployment.yaml
```

### 11.2 Create Namespace

```bash
kubectl create namespace clinova
```

Or apply the namespace from manifests:
```bash
kubectl apply -f - << EOF
apiVersion: v1
kind: Namespace
metadata:
  name: clinova
  labels:
    istio-injection: disabled
EOF
```

### 11.3 Apply ConfigMap

```bash
kubectl apply -f configmap.yaml
```

Verify:
```bash
kubectl get configmap -n clinova
```

### 11.4 Apply Secrets

```bash
kubectl apply -f secrets.yaml
```

Verify:
```bash
kubectl get secrets -n clinova
```

### 11.5 Deploy PostgreSQL

```bash
kubectl apply -f postgres-statefulset.yaml
```

Monitor deployment:
```bash
kubectl get pods -n clinova -l app=postgres -w
```

Wait until status is `Running`.

### 11.6 Deploy Redis

```bash
kubectl apply -f redis-deployment.yaml
```

### 11.7 Run Database Migrations

Once PostgreSQL is ready:

```bash
# Get pod name
POSTGRES_POD=$(kubectl get pods -n clinova -l app=postgres -o jsonpath='{.items[0].metadata.name}')

# Create database and user
kubectl exec -n clinova $POSTGRES_POD -- psql -U postgres -c "CREATE USER penthus WITH PASSWORD 'YourSecureDbPassword123!';"
kubectl exec -n clinova $POSTGRES_POD -- psql -U postgres -c "CREATE DATABASE clinova OWNER penthus;"
kubectl exec -n clinova $POSTGRES_POD -- psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE clinova TO penthus;"
```

### 11.8 Deploy vLLM Service

```bash
kubectl apply -f vllm-deployment.yaml
```

**Important**: vLLM deployment will take 5-10 minutes as it downloads the model.

Monitor:
```bash
kubectl get pods -n clinova -l app=penthus-vllm -w
kubectl logs -n clinova -l app=penthus-vllm -f
```

### 11.9 Deploy API Service

```bash
kubectl apply -f api-deployment.yaml
```

Monitor:
```bash
kubectl get pods -n clinova -l app=clinova-api -w
kubectl logs -n clinova -l app=clinova-api -f
```

### 11.10 Deploy Ingress

```bash
kubectl apply -f ingress.yaml
```

### 11.11 Verify All Deployments

```bash
# Check all pods
kubectl get pods -n clinova

# Expected output:
# NAME                            READY   STATUS    RESTARTS   AGE
# clinova-api-xxxxxxxxxx-xxxxx    1/1     Running   0          5m
# clinova-api-xxxxxxxxxx-xxxxx    1/1     Running   0          5m
# clinova-api-xxxxxxxxxx-xxxxx    1/1     Running   0          5m
# penthus-vllm-xxxxxxxxxx-xxxxx   1/1     Running   0          10m
# postgres-0                      1/1     Running   0          15m
# redis-xxxxxxxxxx-xxxxx          1/1     Running   0          15m

# Check services
kubectl get svc -n clinova

# Check deployments
kubectl get deployments -n clinova

# Check statefulsets
kubectl get statefulsets -n clinova
```

---

## 12. Step 8: Configure Load Balancer and DNS

### 12.1 Get Load Balancer Information

```bash
# Get load balancer IP
kubectl get svc -n clinova clinova-api

# Or get from OCI
oci lb load-balancer list --compartment-id <compartment-ocid>
```

### 12.2 Configure DNS (Optional but Recommended)

1. Get your Load Balancer IP address from previous step
2. Go to your DNS provider (e.g., Route53, Cloudflare, OCI DNS)
3. Create an A record:
   - **Name**: `clinova-api` or `api`
   - **Type**: A
   - **Value**: `<load-balancer-ip>`
   - **TTL**: 300

Example for OCI DNS:
```bash
oci dns record update \
  --zone-name-or-id dasmedhub.com \
  --domain clinova-api.dasmedhub.com \
  --rtype A \
  --items '[{"rdata":"<load-balancer-ip>","ttl":300}]'
```

### 12.3 Set Up SSL/TLS Certificate

#### Option A: Using Let's Encrypt with cert-manager

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Create ClusterIssuer
kubectl apply -f - << EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@dasmedhub.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
    - http01:
        ingress:
          class: nginx
EOF
```

#### Option B: Using OCI Certificate Manager

1. Navigate to **Developer Services** → **Certificates**
2. Click **Create Certificate**
3. Choose certificate authority or import your own
4. Associate with Load Balancer

### 12.4 Update Ingress with TLS

Ensure your ingress.yaml has TLS configured (already in the repository):

```yaml
spec:
  tls:
    - hosts:
        - clinova-api.dasmedhub.com
      secretName: clinova-api-tls
```

---

## 13. Step 9: Verify Deployment

### 13.1 Health Check

```bash
# Get load balancer URL
LB_IP=$(kubectl get svc -n clinova clinova-api -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Test health endpoint
curl -v http://$LB_IP/api/v1/health

# Expected response:
# {"status":"healthy","service":"Penthus-Clinical-AI-Engine","version":"1.2.0"}
```

### 13.2 Test Readiness

```bash
curl -v http://$LB_IP/api/v1/readiness
```

### 13.3 Test OCR Endpoint

```bash
# Create a test request
cat > test-ocr.json << EOF
{
  "tenant_id": "test-tenant",
  "encounter_id": "enc-001",
  "document_id": "doc-001",
  "patient_id": "pat-001",
  "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
  "language": "en"
}
EOF

curl -X POST http://$LB_IP/api/v1/ocr \
  -H "Content-Type: application/json" \
  -d @test-ocr.json
```

### 13.4 Test SOAP Generation

```bash
curl -X POST http://$LB_IP/api/v1/soap \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "tenant_id": "test-tenant",
    "encounter_id": "enc-001",
    "text": "Patient presents with fever and cough for 3 days.",
    "language": "en"
  }'
```

### 13.5 Check Metrics Endpoint

```bash
curl http://$LB_IP/api/v1/metrics
```

### 13.6 Access Swagger Documentation

Open in browser:
```
http://<load-balancer-ip>/docs
```

### 13.7 Monitor Logs

```bash
# View API logs
kubectl logs -n clinova -l app=clinova-api -f

# View vLLM logs
kubectl logs -n clinova -l app=penthus-vllm -f

# View all logs in real-time
stern -n clinova .
```

Install stern for multi-pod log streaming:
```bash
brew install stern  # macOS
# or
wget https://github.com/stern/stern/releases/latest/download/stern_linux_amd64.tar.gz
```

---

## 14. Step 10: Set Up Monitoring and Alerts

### 14.1 Verify OCI Monitoring Integration

Terraform already created alarms. Verify them:

```bash
oci monitoring alarm list --compartment-id <compartment-ocid>
```

### 14.2 Configure Notification Subscription

To receive alerts via email:

1. Navigate to **Developer Services** → **Notifications**
2. Select the topic `clinova-penthus-alerts`
3. Click **Create Subscription**
4. Choose protocol: **Email**
5. Enter email address
6. Click **Create Subscription**
7. Confirm subscription via email

### 14.3 Set Up Grafana Dashboard (Optional)

```bash
# Deploy Prometheus and Grafana
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install monitoring prometheus-community/kube-prometheus-stack -n clinova

# Port forward to access Grafana
kubectl port-forward -n clinova svc/monitoring-grafana 3000:80
```

Access Grafana at `http://localhost:3000` (admin/prom-operator)

### 14.4 Import Custom Dashboards

Import the Clinova-specific dashboards:

1. In Grafana, go to **Dashboards** → **Import**
2. Upload dashboard JSON files from `infra/monitoring/grafana/`
3. Select Prometheus data source

### 14.5 Set Up Log Aggregation

OCI Logging is already configured. Access logs:

1. Navigate to **Observability & Management** → **Logging**
2. Select log group `clinova-penthus-production`
3. View logs from `penthus-api-log`

---

## 15. Troubleshooting

### Common Issues and Solutions

#### Issue 1: Pods Stuck in Pending State

**Symptoms**: Pods show `Pending` status indefinitely

**Causes**:
- Insufficient resources
- GPU node pool not ready
- PVC provisioning issues

**Solutions**:
```bash
# Check pod events
kubectl describe pod <pod-name> -n clinova

# Check node capacity
kubectl describe nodes

# Check PVC status
kubectl get pvc -n clinova
```

#### Issue 2: ImagePullBackOff Errors

**Symptoms**: Pods fail to pull images

**Causes**:
- Incorrect image path
- Authentication issues with OCIR

**Solutions**:
```bash
# Verify image exists
oci artifacts container image list --repo-id <repo-ocid>

# Check image pull secret
kubectl get secrets -n clinova

# Recreate pull secret if needed
kubectl create secret docker-registry ocir-secret \
  --docker-server=us-ashburn-1.ocir.io \
  --docker-username='<tenancy>/<username>' \
  --docker-password='<auth-token>' \
  --docker-email='email@example.com' \
  -n clinova
```

#### Issue 3: vLLM Not Starting

**Symptoms**: vLLM pod crashes or stays in ContainerCreating

**Causes**:
- Model download failure
- Insufficient GPU memory
- Missing GPU drivers

**Solutions**:
```bash
# Check pod logs
kubectl logs -n clinova -l app=penthus-vllm

# Verify GPU is detected
kubectl exec -n clinova <vllm-pod> -- nvidia-smi

# Check node labels
kubectl get nodes --show-labels | grep gpu
```

#### Issue 4: Database Connection Errors

**Symptoms**: API pods crash with database connection errors

**Causes**:
- PostgreSQL not ready
- Incorrect credentials
- Network policy blocking

**Solutions**:
```bash
# Check PostgreSQL status
kubectl get pods -n clinova -l app=postgres

# Test database connectivity
kubectl run -it --rm debug --image=postgres:16-alpine --restart=Never -- psql postgresql://penthus:password@postgres.clinova.svc.cluster.local:5432/clinova

# Check network policies
kubectl get networkpolicies -n clinova
```

#### Issue 5: Load Balancer Not Accessible

**Symptoms**: Cannot reach API endpoints

**Causes**:
- Security list rules incorrect
- Ingress not configured properly
- DNS not propagated

**Solutions**:
```bash
# Check load balancer status
oci lb load-balancer get --load-balancer-id <lb-ocid>

# Verify security lists
oci network security-list list --vcn-id <vcn-id>

# Test direct service IP
kubectl get svc -n clinova clinova-api
```

#### Issue 6: High Latency or Timeouts

**Symptoms**: Requests taking too long or timing out

**Causes**:
- GPU underprovisioned
- Model loading issues
- Network bottlenecks

**Solutions**:
```bash
# Check GPU utilization
kubectl top pods -n clinova

# Monitor vLLM metrics
curl http://<vllm-service>:8000/metrics

# Scale API replicas
kubectl scale deployment clinova-api -n clinova --replicas=5
```

### Debugging Commands Reference

```bash
# Get all resources in namespace
kubectl get all -n clinova

# Describe problematic pod
kubectl describe pod <pod-name> -n clinova

# Execute into pod
kubectl exec -it <pod-name> -n clinova -- /bin/sh

# Port forward for debugging
kubectl port-forward -n clinova <pod-name> 8080:8000

# Check resource usage
kubectl top nodes
kubectl top pods -n clinova

# View events
kubectl get events -n clinova --sort-by='.lastTimestamp'

# Check persistent volumes
kubectl get pv,pvc -n clinova

# Validate YAML syntax
kubectl apply --dry-run=client -f <file>.yaml
```

---

## 16. Cost Optimization Tips

### 16.1 Right-Size Resources

- Start with 1 GPU node for development
- Use auto-scaling for API pods
- Adjust GPU memory utilization based on actual usage

### 16.2 Use Auto-Scaling

```bash
# Enable cluster autoscaler
kubectl apply -f https://raw.githubusercontent.com/kubernetes/autoscaler/master/cluster-autoscaler/cloudprovider/oci/examples/cluster-autoscaler-deployment.yaml

# Configure HPA bounds
kubectl edit hpa clinova-api-hpa -n clinova
```

### 16.3 Schedule Non-Critical Workloads on Spot Instances

```yaml
# Add to node pool configuration
node_config_details:
  placement_configs:
    - subnet_id: <subnet-ocid>
  size: 2
  is_spot_instance: true  # Up to 90% savings
```

### 16.4 Clean Up Development Resources

When not in use:

```bash
# Scale down deployments
kubectl scale deployment clinova-api -n clinova --replicas=0
kubectl scale deployment penthus-vllm -n clinova --replicas=0

# Or delete entire namespace
kubectl delete namespace clinova
```

### 16.5 Monitor Costs

Set up OCI Budget alerts:

1. Navigate to **Governance & Administration** → **Budgets**
2. Create budget with monthly threshold
3. Set up email alerts at 50%, 80%, 100%

---

## Appendix A: Quick Reference Commands

### OCI CLI Commands

```bash
# List compartments
oci iam compartment list --compartment-id-in-subtree=true

# Get cluster info
oci ce cluster get --cluster-id <ocid>

# List node pools
oci ce node-pool list --cluster-id <ocid>

# List load balancers
oci lb load-balancer list --compartment-id <compartment-ocid>

# List object storage buckets
oci os bucket list --namespace <namespace>

# Get vault secrets
oci vault secret list --vault-id <vault-ocid>
```

### kubectl Commands

```bash
# Context switching
kubectl config get-contexts
kubectl config use-context <context-name>

# Resource management
kubectl get pods -n clinova -o wide
kubectl get deployments -n clinova
kubectl get services -n clinova
kubectl get ingress -n clinova

# Scaling
kubectl scale deployment <name> -n clinova --replicas=3

# Rolling updates
kubectl rollout restart deployment/<name> -n clinova
kubectl rollout status deployment/<name> -n clinova

# Rollback
kubectl rollout undo deployment/<name> -n clinova
```

### Terraform Commands

```bash
# State management
terraform state list
terraform state show <resource>
terraform state rm <resource>

# Refresh state
terraform refresh

# Import existing resources
terraform import <resource_type>.<resource_name> <resource_id>

# Destroy infrastructure (CAUTION!)
terraform destroy
```

---

## Appendix B: Security Best Practices

### 1. Never Commit Secrets

- Use `.gitignore` for sensitive files
- Use OCI Vault for secret management
- Rotate secrets regularly

### 2. Enable Private Endpoints

- Keep vLLM internal-only
- Use private subnets for databases
- Restrict security list rules

### 3. Implement RBAC

```bash
# Create limited service accounts
kubectl create serviceaccount clinova-reader -n clinova
kubectl create clusterrole reader --verb=get,list --resource=pods,services
kubectl create rolebinding clinova-reader-binding --clusterrole=reader --serviceaccount=clinova:clinova-reader
```

### 4. Enable Audit Logging

All OCI API calls are logged automatically. Access via:
**Governance & Administration** → **Audit**

### 5. Regular Security Updates

```bash
# Update base images
docker pull python:3.12-slim
docker pull postgres:16-alpine
docker pull redis:7-alpine

# Rebuild and redeploy
docker build -t ... && docker push ...
kubectl rollout restart deployment/...
```

---

## Appendix C: Backup and Disaster Recovery

### Database Backups

```bash
# Manual backup
kubectl exec -n clinova postgres-0 -- pg_dump -U penthus clinova > backup.sql

# Automated backups with OCI Database Backup Service
# (Recommended for production - migrate to OCI Autonomous Database)
```

### Object Storage Versioning

Enable versioning on buckets:
```bash
oci os bucket update --namespace <ns> --bucket-name clinova-documents --is-versioning-enabled true
```

### Disaster Recovery Plan

1. **Backup Terraform state** regularly
2. **Export Kubernetes manifests**: `kubectl get all -n clinova -o yaml > backup.yaml`
3. **Document recovery procedures**
4. **Test recovery quarterly**

---

## Conclusion

Congratulations! You have successfully deployed the Clinova Penthus AI Engine to Oracle Cloud Infrastructure. The system is now running with:

- ✅ OKE cluster with CPU and GPU node pools
- ✅ FastAPI clinical AI orchestrator
- ✅ vLLM model serving with GPU acceleration
- ✅ PostgreSQL database for persistence
- ✅ Redis caching layer
- ✅ OCI Load Balancer for traffic distribution
- ✅ OCI Vault for secret management
- ✅ Monitoring and alerting configured

### Next Steps

1. **Configure CI/CD Pipeline**: Set up automated deployments with GitHub Actions or OCI DevOps
2. **Implement Multi-Tenancy**: Configure tenant isolation and billing
3. **Performance Testing**: Load test with realistic clinical workloads
4. **Security Audit**: Conduct penetration testing and compliance review
5. **Documentation**: Create runbooks for operations team

### Support Resources

- **OCI Documentation**: https://docs.oracle.com/en-us/iaas/
- **Kubernetes Documentation**: https://kubernetes.io/docs/
- **Terraform OCI Provider**: https://registry.terraform.io/providers/oracle/oci/latest/docs
- **Project Issues**: Contact engineering@dasmedhub.com

---

*Last Updated: June 2025*  
*Version: 1.0*
