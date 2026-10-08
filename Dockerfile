# CPU-only image for the autocrop CLI (stage 06).
FROM python:3.12-slim

# System libraries strictly required at runtime (OpenCV via ultralytics).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists

WORKDIR /app

# Writable HOME for the host UID/GID configured in compose.yaml
# (Ultralytics writes its config under $HOME on first run).
ENV HOME=/tmp/home \
    XDG_CONFIG_HOME=/tmp/home/.config \
    MPLCONFIGDIR=/tmp/home/.config/matplotlib
RUN mkdir -p /tmp/home/.config && chmod -R 777 /tmp/home

# CPU-only PyTorch from the CPU-only index, with no PyPI fallback:
# a future CUDA default on PyPI must never leak into this image.
# The later PyPI install keeps this torch (already satisfying) untouched.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch torchvision

# Remaining runtime deps from PyPI.
RUN pip install --no-cache-dir "ultralytics" "Pillow"

# Project metadata + code. Weights come from the local file; building
# without yolo11n.pt fails here instead of downloading anything later.
COPY pyproject.toml README.md ./
COPY app ./app
COPY yolo11n.pt ./yolo11n.pt
RUN pip install --no-cache-dir --no-deps . \
    && pip check

CMD ["sleep", "infinity"]
