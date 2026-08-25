FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a

ARG WUKONG_RCLONE_RELEASE=1.75.0
ARG WUKONG_RCLONE_LINUX_AMD64_SHA256=aa2804e08f48250e71009c727124b6341cd0288465804a9a09d14663cabafbaa

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PORT=8080 \
    WUKONG_STUDIO_DATA_ROOT=/tmp/wukong/data \
    WUKONG_STUDIO_WORKSPACE_ROOT=/tmp/wukong/workspace \
    WUKONG_STUDIO_OUTPUT_ROOT=/tmp/wukong/output \
    WUKONG_STUDIO_TEMP_ROOT=/tmp/wukong/temp \
    WUKONG_STUDIO_LOG_ROOT=/tmp/wukong/logs \
    WUKONG_STUDIO_CONTENT_ROOT=/app \
    WUKONG_RCLONE_CONFIG=/run/secrets/rclone.conf

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gosu unzip \
    && curl --fail --location --silent --show-error \
        "https://downloads.rclone.org/v${WUKONG_RCLONE_RELEASE}/rclone-v${WUKONG_RCLONE_RELEASE}-linux-amd64.zip" \
        --output /tmp/rclone.zip \
    && echo "${WUKONG_RCLONE_LINUX_AMD64_SHA256}  /tmp/rclone.zip" | sha256sum --check --strict \
    && unzip -q /tmp/rclone.zip -d /tmp/rclone \
    && install -o root -g root -m 0755 \
        "/tmp/rclone/rclone-v${WUKONG_RCLONE_RELEASE}-linux-amd64/rclone" \
        /usr/local/bin/rclone \
    && rm -rf /tmp/rclone /tmp/rclone.zip /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
COPY deploy/control-plane/requirements.txt ./deploy/control-plane/requirements.txt
RUN python -m pip install --no-cache-dir \
    -r requirements.txt \
    -r deploy/control-plane/requirements.txt

COPY . .
RUN useradd --system --uid 10001 --home /tmp/wukong --shell /usr/sbin/nologin wukong \
    && mkdir -p /tmp/wukong/data /tmp/wukong/workspace /tmp/wukong/output /tmp/wukong/temp /tmp/wukong/logs \
    && chown -R wukong:wukong /tmp/wukong \
    && chmod 0755 /app/deploy/cloud-run/entrypoint.sh

USER root
ENTRYPOINT ["/app/deploy/cloud-run/entrypoint.sh"]
CMD ["gunicorn", "--config", "/app/deploy/cloud-run/gunicorn.conf.py", "wukong.cloud_run_app:app"]
