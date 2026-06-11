# Clinova Penthus AI Engine — Repository Overview & Production Runbook

This single document replaces the previous fragmented markdown files. It explains the repository structure, important configuration, deployment options, and step-by-step production runbook to get the AI Engine running on an OCI Ubuntu VM using OCIR images.

---

## 1) High-level summary
- Purpose: FastAPI-based Clinical AI Orchestrator providing OCR, SOAP generation, entity extraction, summarization, translation, FHIR mapping, and gap detection using a single vLLM model endpoint.
- Runtime: Docker containers orchestrated via Docker Compose (single-host). Models served by vLLM (GPU recommended; vllm-mock available for CPU testing).

---

## 2) Important repository locations
- Root: `pyproject.toml`, `alembic.ini`, `.env.example`
- Application code: `app/` (API, orchestrator, db, llm, prompts, services, core)
- Prompts: `prompts/` (YAML templates for workflows)
- Infra: `infra/`
  - `infra/docker/api.Dockerfile` — API image
  - `infra/compose/docker-compose.yml` — production compose
  - `infra/compose/deployment.sh` — build/pull, start, migrate, verify
  - `infra/oci/deploy_with_oci_cli.sh` — helper to launch VM and bootstrap
- Tests: `tests/`
- Docs: `docs/REPO_OVERVIEW.md` (this file)

---

## 3) Key configuration and secrets
- Primary config source during deployment: `/home/<user>/penthus/.env` (or `.env` in repo when building locally).
- Required production variables (minimum):
  - `DB_PASSWORD`, `SECRET_KEY`, `HF_TOKEN` (Hugging Face), `USE_REMOTE_IMAGE=true`, `OCIR_REGISTRY`, `OCIR_REPOSITORY`, `IMAGE_TAG`.
  - Optional: `OBJECT_STORAGE_*` (MinIO or OCI), `REDIS_PASSWORD` (if enabled), `VAULT_*_OCID` (if using Vault fetching on VM).

Security notes:
- Never commit `.env` to git. Use OCI Vault or GitHub Secrets for CI.
- OCIR Docker login uses an Auth Token created in OCI Console (Identity → Users → Auth Tokens).

---

## 4) Build & publish (recommended production flow — OCIR)
Local (developer machine / CI):

1. Build API image:
   ```bash
   docker build -f infra/docker/api.Dockerfile -t ${OCIR_REGISTRY}/${OCIR_REPOSITORY}:api-${IMAGE_TAG} .
   ```
2. Login to OCIR using your tenancy namespace and Auth Token:
   ```bash
   docker login ${OCIR_REGISTRY} -u "${NAMESPACE}/${OCI_USERNAME}" --password-stdin
   ```
3. Push image:
   ```bash
   docker push ${OCIR_REGISTRY}/${OCIR_REPOSITORY}:api-${IMAGE_TAG}
   ```

CI: a GitHub Actions workflow `/.github/workflows/oci-ci.yml` is included to build and push the API image. Set repository secrets: `OCIR_REGISTRY`, `OCIR_REPOSITORY`, `OCIR_USERNAME`, `OCIR_AUTH_TOKEN`.

---

## 5) VM preparation (Ubuntu 22.04) — minimal checklist
1. SSH into VM and stop conflicting services (e.g., Apache):
   ```bash
   sudo systemctl stop apache2 && sudo systemctl disable apache2
   ```
2. Install Docker and Compose plugin (or let `deployment.sh` attempt installs):
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   sudo apt install -y docker-compose-plugin
   ```
3. If GPU required: install NVIDIA drivers + NVIDIA Container Toolkit (see step-by-step below).
4. Ensure repo is present at `/home/<user>/penthus` (tarball flow in `infra/oci/deploy_with_oci_cli.sh` transfers the code).

GPU driver + toolkit (summary):
```bash
sudo apt update
sudo apt install -y build-essential dkms linux-headers-$(uname -r) curl wget git jq
sudo add-apt-repository -y ppa:graphics-drivers/ppa
sudo apt update
sudo apt install -y nvidia-driver-535
sudo reboot
# after reboot
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update
sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
``` 

---

## 6) Deployment on VM (pull from OCIR)
1. Place `.env` in `/home/<user>/penthus/.env` with at minimum `USE_REMOTE_IMAGE=true`, `OCIR_REGISTRY`, `OCIR_REPOSITORY`, `IMAGE_TAG`, and secrets.
2. Docker login on VM:
   ```bash
   docker login $OCIR_REGISTRY -u "${NAMESPACE}/${OCI_USERNAME}"
   # paste Auth Token
   ```
3. Run deployment script (pulls image, starts services, runs Alembic migrations):
   ```bash
   cd /home/<user>/penthus/infra/compose
   sudo -E ./deployment.sh deploy
   ```

Notes: `deployment.sh` waits for Postgres readiness and runs `docker exec penthus-api alembic upgrade head` to apply migrations.

---

## 7) Post-deploy verification
- Check containers: `docker ps -a`
- API logs: `docker compose -f docker-compose.yml logs -f api`
- Health: `curl -sSf http://localhost/api/v1/health`
- vLLM health: `docker exec penthus-vllm curl -s http://localhost:8000/health` (or vllm-mock if CPU)

---

## 8) Database creation & migrations
- `deployment.sh` runs Alembic migrations inside the running `penthus-api` container.
- If you need to run manually after DB provisioning:
  ```bash
  docker exec -it penthus-api alembic upgrade head
  ```
- If you provision a managed PostgreSQL separately, ensure `DATABASE_URL` points to the correct host and `DB_PASSWORD` is set.

---

## 9) Cleanup, logs, and troubleshooting
- Disk: model images may be tens of GB — monitor `df -h` and `docker system df`.
- Clean images: `docker system prune -a` (only when safe).
- If a service fails to start, inspect logs and status:
  - `docker compose -f docker-compose.yml ps`
  - `docker compose -f docker-compose.yml logs api`

---

## 10) Maintenance suggestions
- Use OCIR + CI for image management and automated deploys.
- Move secrets to OCI Vault and fetch on bootstrap (scripts included support Vault OCIDs).
- Add systemd unit to ensure `deployment.sh deploy` runs on reboot (or use Docker restart policies).

---

If you want, I will now:
- run a repo-wide sweep to remove any other markdown files (already removed),
- produce a small `deploy-prod.sh` you can run on the VM to perform final checks and start deployment, or
- SSH into the VM with your guidance and complete the deployment steps interactively.

Choose which next action you want me to take.
