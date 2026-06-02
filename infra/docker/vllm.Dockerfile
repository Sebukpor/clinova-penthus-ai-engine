# ============================================
# Clinova Penthus AI Engine - vLLM Dockerfile
# Penthus Model: Sebukpor/medical-document-understanding-v2-fixed
# Served with vLLM OpenAI-compatible API
# ============================================

FROM vllm/vllm-openai:latest AS base

# Build arguments for model configuration
ARG HF_TOKEN=""
ARG MODEL_REPO="Sebukpor/medical-document-understanding-v2-fixed"
ARG SERVED_MODEL_NAME="penthus-1.2-alpha-4b"
ARG MAX_MODEL_LEN=8192
ARG GPU_MEMORY_UTILIZATION=0.90
ARG DTYPE="bfloat16"

ENV HF_TOKEN=${HF_TOKEN} \
    MODEL_REPO=${MODEL_REPO} \
    SERVED_MODEL_NAME=${SERVED_MODEL_NAME} \
    MAX_MODEL_LEN=${MAX_MODEL_LEN} \
    GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION} \
    DTYPE=${DTYPE} \
    PORT=8000 \
    VLLM_PORT=8000

# Create model cache directory
RUN mkdir -p /models && chmod 755 /models

# Download model if HF_TOKEN provided
# In production, use init container or pre-downloaded model volume
RUN if [ -n "$HF_TOKEN" ]; then \
        pip install huggingface-hub && \
        huggingface-cli login --token $HF_TOKEN && \
        huggingface-cli download $MODEL_REPO --local-dir /models/$MODEL_REPO --local-dir-use-symlinks False; \
    fi

EXPOSE 8000

# vLLM startup command
# In production, the model path should be a persistent volume
# mounted from OCI Object Storage or pre-built image
CMD python -m vllm.entrypoints.openai.api_server \
    --model /models/${MODEL_REPO} \
    --served-model-name ${SERVED_MODEL_NAME} \
    --host 0.0.0.0 \
    --port 8000 \
    --dtype ${DTYPE} \
    --max-model-len ${MAX_MODEL_LEN} \
    --gpu-memory-utilization ${GPU_MEMORY_UTILIZATION} \
    --enable-prefix-caching \
    --trust-remote-code
