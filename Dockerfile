FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LAYA_IMAGE_CACHE=/opt/hf-cache \
    HF_HOME=/opt/hf-cache \
    ENGINE=laya \
    LAYA_PRELOAD=true \
    LAYA_DEVICE=cpu

COPY pyproject.toml README.md ./
COPY src ./src
COPY docker/entrypoint.sh /entrypoint.sh

# CPU wheels: a CUDA build is several GB and needs nvidia-container-toolkit on the host.
RUN chmod +x /entrypoint.sh \
    && pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir '.[engine]'

# Bake checkpoints into the image. At runtime they are copied into the Kamal volume.
RUN python -m laya_api.download_models

ENV HF_HOME=/data/huggingface
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "laya_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
