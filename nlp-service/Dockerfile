FROM python:3.11-slim

# Tesseract with Malay + English language data. System packages need root, so
# they are installed before switching to the unprivileged user below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-msa \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces run the container as UID 1000. Building as that same user
# keeps everything it writes at runtime writable, including the Hub download
# cache under $HOME/.cache/huggingface.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# Requirements before code: this layer is rebuilt only when requirements.txt
# changes, not on every code edit. --user installs into ~/.local, whose bin/ is
# on PATH above (that is where the uvicorn command lands).
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# The Hub download cache, created as `user`. This matters when a Docker volume
# is mounted here to keep the weights between runs: a new volume takes the
# owner of the directory it covers, so without this it would belong to root
# and the download would fail with "Permission denied". Placed after the pip
# layer so a rebuild reuses that cached layer.
RUN mkdir -p $HOME/.cache/huggingface

# No model weights in the image (.dockerignore excludes models/). Set
# FINETUNED_MODEL_DIR to a Hub repo id, plus HF_TOKEN for a private repo.
COPY --chown=user . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
