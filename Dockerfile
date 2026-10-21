FROM debian:trixie-slim
LABEL org.opencontainers.image.authors="Jurre van der Gaag - Terpstra <jurre@terpstra.tech>"
LABEL org.opencontainers.image.source="https://github.com/jterpstra1/grimmory-convert"

RUN apt-get update && \
    apt-get install -y --no-install-recommends calibre python3 tzdata && \
    rm -rf /var/lib/apt/lists/*

# Calibre needs a Qt platform even for command-line conversion; HOME holds its config.
ENV QT_QPA_PLATFORM=offscreen HOME=/tmp PYTHONUNBUFFERED=1 \
    LIBRARY_DIR=/books STATE_DIR=/config

COPY convert.py /app/convert.py

# Unraid's nobody:users, so converted files get the same owner as the rest of the share.
USER 99:100
ENTRYPOINT ["python3", "/app/convert.py"]
