FROM python:3.13-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a

ARG WUKONG_RCLONE_RELEASE=1.75.0
ARG WUKONG_RCLONE_LINUX_AMD64_SHA256=aa2804e08f48250e71009c727124b6341cd0288465804a9a09d14663cabafbaa

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    WUKONG_STUDIO_DATA_ROOT=/var/lib/wukong/data \
    WUKONG_STUDIO_WORKSPACE_ROOT=/var/lib/wukong/workspace \
    WUKONG_STUDIO_OUTPUT_ROOT=/var/lib/wukong/output \
    WUKONG_STUDIO_TEMP_ROOT=/var/lib/wukong/temp \
    WUKONG_STUDIO_LOG_ROOT=/var/lib/wukong/logs \
    WUKONG_STUDIO_CONTENT_ROOT=/app \
    WUKONG_RCLONE_CONFIG=/var/lib/wukong/data/Secrets/rclone.runtime.conf \
    WUKONG_TELEGRAM_MINI_APP_API_BIND=0.0.0.0 \
    WUKONG_TELEGRAM_MINI_APP_API_PORT=8766

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
    && rclone version | grep -F "rclone v${WUKONG_RCLONE_RELEASE}" \
    && rm -rf /tmp/rclone /tmp/rclone.zip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /var/lib/wukong/data /var/lib/wukong/workspace /var/lib/wukong/output /var/lib/wukong/temp /var/lib/wukong/logs \
    && useradd --system --uid 10001 --home /var/lib/wukong --shell /usr/sbin/nologin wukong \
    && chown -R wukong:wukong /var/lib/wukong \
    && chmod 0755 /app/deploy/control-plane/entrypoint.sh

EXPOSE 8766 10000
ENTRYPOINT ["/app/deploy/control-plane/entrypoint.sh"]
CMD ["python", "telegram_bot_daemon.py"]
