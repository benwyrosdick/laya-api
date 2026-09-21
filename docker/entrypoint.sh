#!/bin/sh
set -e

HF_HOME="${HF_HOME:-/data/huggingface}"
IMAGE_CACHE="${LAYA_IMAGE_CACHE:-/opt/hf-cache}"

mkdir -p "$HF_HOME"

# Seed the persistent volume from checkpoints baked into the image.
# -n: do not overwrite files already downloaded on the host.
if [ -d "$IMAGE_CACHE/hub" ]; then
  echo "Seeding Hugging Face cache into $HF_HOME"
  cp -an "$IMAGE_CACHE/." "$HF_HOME/"
fi

exec "$@"
