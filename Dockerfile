FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/root/.cache/huggingface \
    ENGINE=laya \
    LAYA_PRELOAD=true \
    LAYA_DEVICE=cpu

COPY pyproject.toml README.md ./
COPY src ./src

# CPU wheels: a CUDA build is several GB and needs nvidia-container-toolkit on the host.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir '.[engine]'

# Bake the three Laya checkpoints into the image so boot does not hit Hugging Face.
RUN python -m laya_api.download_models

EXPOSE 8000
CMD ["uvicorn", "laya_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
