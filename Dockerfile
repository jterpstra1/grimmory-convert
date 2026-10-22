FROM debian:trixie-slim
LABEL org.opencontainers.image.authors="Jurre van der Gaag - Terpstra <jurre@terpstra.tech>"
LABEL org.opencontainers.image.source="https://github.com/jterpstra1/grimmory-convert"

RUN apt-get update && \
    apt-get install -y --no-install-recommends calibre python3 tzdata && \
    rm -rf /var/lib/apt/lists/*

# Calibre needs a Qt platform even for command-line conversion. Its config (and the plugins
# installed from /plugins) lives in /tmp and is rebuilt on every start.
ENV QT_QPA_PLATFORM=offscreen HOME=/tmp PYTHONUNBUFFERED=1 \
    CALIBRE_CONFIG_DIRECTORY=/tmp/calibre-config \
    LIBRARY_DIR=/books STATE_DIR=/config PLUGINS_DIR=/plugins

COPY convert.py /app/convert.py

# Unraid's nobody:users, so converted files get the same owner as the rest of the share.
USER 99:100
ENTRYPOINT ["python3", "/app/convert.py"]
