#!/usr/bin/env bash
# OCI CLI deployment helper for Clinova Penthus AI Engine
# Usage: ./deploy_with_oci_cli.sh --compartment <compartment-ocid> --subnet <subnet-ocid> --image <image-ocid> --shape <shape> --ssh-key ~/.ssh/id_rsa.pub --git-url <repo-url>
# After running and logging into OCI CLI (`oci session authenticate`), this script will:
# 1. Launch an OCI compute instance (GPU shape by default)
# 2. Wait for public IP
# 3. SSH into the instance and bootstrap Docker, NVIDIA runtime (optional), and Docker Compose
# 4. Clone the repo and run infra/compose/deployment.sh deploy

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
  cat <<EOF
Usage: $0 --compartment COMPARTMENT_OCID --subnet SUBNET_OCID --image IMAGE_OCID --shape SHAPE --ssh-key PATH_TO_PUBKEY --git-url GIT_URL [--display-name NAME] [--ocpus OCPUS] [--memory MEM_GB]

Example:
  $0 \ 
    --compartment ocid1.compartment.oc1..aaaaaaaaxxx \ 
    --subnet ocid1.subnet.oc1..aaaaaaaaxx \ 
    --image ocid1.image.oc1..aaaaaaaaxxx \ 
    --shape BM.GPU.A10.1 \ 
    --ssh-key ~/.ssh/id_rsa.pub \ 
    --git-url git@github.com:me/clinova-penthus-ai-engine.git

Notes:
- If your repository is private, ensure the VM has access (use SSH deploy key or set GIT_URL to an HTTPS URL and provide credentials).
- The script uses `oci compute instance launch` and requires the OCI CLI configured and authenticated.
EOF
  exit 1
}

# Parse args
COMPARTMENT_OCID=""
SUBNET_OCID=""
IMAGE_OCID=""
SHAPE="BM.GPU.A10.1"
SSH_KEY_PUB=""
GIT_URL=""
DISPLAY_NAME="penthus-ai-vm"
OCPUS=1
MEM_GB=8

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compartment) COMPARTMENT_OCID="$2"; shift 2;;
    --subnet) SUBNET_OCID="$2"; shift 2;;
    --image) IMAGE_OCID="$2"; shift 2;;
    --shape) SHAPE="$2"; shift 2;;

    # Forward optional Vault OCIDs and registry settings to remote bootstrap
    EXPORTS=""
    if [[ -n "${VAULT_DB_SECRET_OCID:-}" ]]; then
      EXPORTS+="export VAULT_DB_SECRET_OCID='${VAULT_DB_SECRET_OCID}'; "
    fi
    if [[ -n "${VAULT_SECRET_KEY_OCID:-}" ]]; then
      EXPORTS+="export VAULT_SECRET_KEY_OCID='${VAULT_SECRET_KEY_OCID}'; "
    fi
    if [[ -n "${VAULT_HF_TOKEN_OCID:-}" ]]; then
      EXPORTS+="export VAULT_HF_TOKEN_OCID='${VAULT_HF_TOKEN_OCID}'; "
    fi
    if [[ -n "${OCIR_REGISTRY:-}" ]]; then
      EXPORTS+="export OCIR_REGISTRY='${OCIR_REGISTRY}'; "
    fi
    if [[ -n "${OCIR_REPOSITORY:-}" ]]; then
      EXPORTS+="export OCIR_REPOSITORY='${OCIR_REPOSITORY}'; "
    fi
    if [[ -n "${IMAGE_TAG:-}" ]]; then
      EXPORTS+="export IMAGE_TAG='${IMAGE_TAG}'; "
    fi
    if [[ -n "${USE_REMOTE_IMAGE:-}" ]]; then
      EXPORTS+="export USE_REMOTE_IMAGE='${USE_REMOTE_IMAGE}'; "
    fi

    echo "Copying code tarball to instance..."
    # Use scp to copy tarball to remote instance (assumes SSH key access)
    scp -o StrictHostKeyChecking=no "$CODE_TARBALL" opc@"$OCI_IP":/home/opc/penthus_code.tar.gz

    BOOTSTRAP_SCRIPT=$(cat <<EOF
    set -euo pipefail
    ${EXPORTS}
    # Update and install required packages
    if command -v dnf &> /dev/null; then
      sudo dnf update -y
      sudo dnf install -y git curl wget python3-pip tar jq
    elif command -v apt-get &> /dev/null; then
      sudo apt-get update -y
      sudo apt-get install -y git curl wget python3-pip tar jq
    fi

    # Install Docker
    if ! command -v docker &> /dev/null; then
      curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
      sudo sh /tmp/get-docker.sh
      sudo usermod -aG docker "$USER"
      sudo systemctl enable --now docker
    fi

    # Install Docker Compose plugin (if missing)
    if ! docker compose version &> /dev/null; then
      sudo apt-get install -y docker-compose-plugin || true
    fi

    # Optionally check NVIDIA runtime if GPU instance
    if command -v nvidia-smi &> /dev/null; then
      echo "NVIDIA drivers present"
    else
      echo "NVIDIA drivers not detected; if this is a GPU instance, install drivers per vendor docs"
    fi

    # Ensure OCI CLI available for fetching Vault secrets if OCIDs provided
    if command -v oci &> /dev/null; then
      echo "OCI CLI present"
    else
      echo "Installing OCI CLI (user-level)..."
      python3 -m pip install --user oci-cli || true
      export PATH="${HOME}/.local/bin:$PATH"
    fi

    # Extract provided code tarball
    if [[ -f /home/opc/penthus_code.tar.gz ]]; then
      mkdir -p /home/opc/penthus
      tar -xzf /home/opc/penthus_code.tar.gz -C /home/opc/penthus
      chown -R "$USER":"$USER" /home/opc/penthus || true
    else
      echo "Code tarball not found on instance; aborting"
      exit 1
    fi

    # Function to fetch secret from OCI Vault (returns decoded value)
    fetch_secret() {
      local secret_ocid="$1"
      if [[ -z "$secret_ocid" ]]; then
        return 1
      fi
      # The secret content is base64 encoded in data."secret-bundle-content"."content"
      secret_b64=$(oci vault secret-bundle get --secret-id "$secret_ocid" --query 'data."secret-bundle-content"."content"' --raw-output 2>/dev/null || true)
      if [[ -n "$secret_b64" ]]; then
        echo "$secret_b64" | base64 --decode
        return 0
      fi
      return 1
    }

    # Collect secrets into a temporary env file
    SECRETS_FILE="/home/opc/penthus/.env.secrets"
    rm -f "$SECRETS_FILE"
    touch "$SECRETS_FILE"

    if [[ -n "${VAULT_DB_SECRET_OCID:-}" ]]; then
      echo "Fetching DB password from Vault..."
      dbpw=$(fetch_secret "$VAULT_DB_SECRET_OCID" || true)
      if [[ -n "$dbpw" ]]; then
        echo "DB_PASSWORD=$dbpw" >> "$SECRETS_FILE"
      fi
    fi

    if [[ -n "${VAULT_SECRET_KEY_OCID:-}" ]]; then
      echo "Fetching SECRET_KEY from Vault..."
      sk=$(fetch_secret "$VAULT_SECRET_KEY_OCID" || true)
      if [[ -n "$sk" ]]; then
        echo "SECRET_KEY=$sk" >> "$SECRETS_FILE"
      fi
    fi

    if [[ -n "${VAULT_HF_TOKEN_OCID:-}" ]]; then
      echo "Fetching HF_TOKEN from Vault..."
      hft=$(fetch_secret "$VAULT_HF_TOKEN_OCID" || true)
      if [[ -n "$hft" ]]; then
        echo "HF_TOKEN=$hft" >> "$SECRETS_FILE"
      fi
    fi

    # Merge secrets into project .env (do not overwrite any existing non-empty vars)
    PROJECT_ENV="/home/opc/penthus/.env"
    if [[ -f "$SECRETS_FILE" ]]; then
      mkdir -p /home/opc/penthus
      if [[ -f "$PROJECT_ENV" ]]; then
        # Append secrets only if variables are not already present
        while IFS= read -r line; do
          key=${line%%=*}
          if ! grep -q "^${key}=" "$PROJECT_ENV"; then
            echo "$line" >> "$PROJECT_ENV"
          fi
        done < "$SECRETS_FILE"
      else
        cp "$SECRETS_FILE" "$PROJECT_ENV"
      fi
    fi

    cd /home/opc/penthus/infra/compose
    chmod +x deployment.sh
    sudo ./deployment.sh deploy || (echo "deployment script failed; check logs" && exit 1)
    EOF

    # Run the bootstrap script remotely via SSH
    echo "Running bootstrap script on instance..."
    ssh -o StrictHostKeyChecking=no opc@"$OCI_IP" 'bash -s' < <(echo "$BOOTSTRAP_SCRIPT")

    echo "Cleaning up local tarball: $CODE_TARBALL"
    rm -f "$CODE_TARBALL"
elif command -v apt-get &> /dev/null; then
  sudo apt-get update -y
  sudo apt-get install -y git curl wget python3-pip tar jq
fi

# Install Docker
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sudo sh /tmp/get-docker.sh
  sudo usermod -aG docker "$USER"
  sudo systemctl enable --now docker
fi

# Install Docker Compose plugin (if missing)
if ! docker compose version &> /dev/null; then
  sudo apt-get install -y docker-compose-plugin || true
fi

# Optionally check NVIDIA runtime if GPU instance
if command -v nvidia-smi &> /dev/null; then
  echo "NVIDIA drivers present"
else
  echo "NVIDIA drivers not detected; if this is a GPU instance, install drivers per vendor docs"
fi

# Ensure OCI CLI available for fetching Vault secrets if OCIDs provided
if command -v oci &> /dev/null; then
  echo "OCI CLI present"
else
  echo "Installing OCI CLI (user-level)..."
  python3 -m pip install --user oci-cli || true
  export PATH="${HOME}/.local/bin:$PATH"
fi

# Extract provided code tarball
if [[ -f /home/opc/penthus_code.tar.gz ]]; then
  mkdir -p /home/opc/penthus
  tar -xzf /home/opc/penthus_code.tar.gz -C /home/opc/penthus
  chown -R "$USER":"$USER" /home/opc/penthus || true
else
  echo "Code tarball not found on instance; aborting"
  exit 1
fi

# Function to fetch secret from OCI Vault (returns decoded value)
fetch_secret() {
  local secret_ocid="$1"
  if [[ -z "$secret_ocid" ]]; then
    return 1
  fi
  # The secret content is base64 encoded in data."secret-bundle-content"."content"
  secret_b64=$(oci vault secret-bundle get --secret-id "$secret_ocid" --query 'data."secret-bundle-content"."content"' --raw-output 2>/dev/null || true)
  if [[ -n "$secret_b64" ]]; then
    echo "$secret_b64" | base64 --decode
    return 0
  fi
  return 1
}

# Collect secrets into a temporary env file
SECRETS_FILE="/home/opc/penthus/.env.secrets"
rm -f "$SECRETS_FILE"
touch "$SECRETS_FILE"

if [[ -n "${VAULT_DB_SECRET_OCID:-}" ]]; then
  echo "Fetching DB password from Vault..."
  dbpw=$(fetch_secret "$VAULT_DB_SECRET_OCID" || true)
  if [[ -n "$dbpw" ]]; then
    echo "DB_PASSWORD=$dbpw" >> "$SECRETS_FILE"
  fi
fi

if [[ -n "${VAULT_SECRET_KEY_OCID:-}" ]]; then
  echo "Fetching SECRET_KEY from Vault..."
  sk=$(fetch_secret "$VAULT_SECRET_KEY_OCID" || true)
  if [[ -n "$sk" ]]; then
    echo "SECRET_KEY=$sk" >> "$SECRETS_FILE"
  fi
fi

if [[ -n "${VAULT_HF_TOKEN_OCID:-}" ]]; then
  echo "Fetching HF_TOKEN from Vault..."
  hft=$(fetch_secret "$VAULT_HF_TOKEN_OCID" || true)
  if [[ -n "$hft" ]]; then
    echo "HF_TOKEN=$hft" >> "$SECRETS_FILE"
  fi
fi

# Merge secrets into project .env (do not overwrite any existing non-empty vars)
PROJECT_ENV="/home/opc/penthus/.env"
if [[ -f "$SECRETS_FILE" ]]; then
  mkdir -p /home/opc/penthus
  if [[ -f "$PROJECT_ENV" ]]; then
    # Append secrets only if variables are not already present
    while IFS= read -r line; do
      key=${line%%=*}
      if ! grep -q "^${key}=" "$PROJECT_ENV"; then
        echo "$line" >> "$PROJECT_ENV"
      fi
    done < "$SECRETS_FILE"
  else
    cp "$SECRETS_FILE" "$PROJECT_ENV"
  fi
fi

cd /home/opc/penthus/infra/compose
chmod +x deployment.sh

# If requested, construct API_IMAGE from OCIR settings so deployment can pull it
if [[ "${USE_REMOTE_IMAGE:-}" == "true" && -n "${OCIR_REGISTRY:-}" && -n "${OCIR_REPOSITORY:-}" ]]; then
  export API_IMAGE="${OCIR_REGISTRY}/${OCIR_REPOSITORY}:api-${IMAGE_TAG:-latest}"
  echo "Using remote API image: $API_IMAGE"
fi

# Use sudo -E to preserve exported environment variables for deployment
sudo -E ./deployment.sh deploy || (echo "deployment script failed; check logs" && exit 1)
EOF

# Run the bootstrap script remotely via SSH
echo "Running bootstrap script on instance..."
ssh -o StrictHostKeyChecking=no opc@"$OCI_IP" 'bash -s' < <(echo "$BOOTSTRAP_SCRIPT")

echo "Cleaning up local tarball: $CODE_TARBALL"
rm -f "$CODE_TARBALL"

echo "$BOOTSTRAP_SCRIPT" > /tmp/penthus_bootstrap.sh
chmod +x /tmp/penthus_bootstrap.sh

# Use ssh with any configured key agent; assume user has private key locally
ssh -o StrictHostKeyChecking=no opc@"$OCI_IP" 'bash -s' < /tmp/penthus_bootstrap.sh

echo "Deployment initiated. Check Docker Compose services and logs via SSH or OCI Console."

# Print helpful next commands
cat <<EOF
Next steps:
  ssh opc@${OCI_IP}
  docker compose -f infra/compose/docker-compose.yml ps
  docker compose -f infra/compose/docker-compose.yml logs -f api
EOF
