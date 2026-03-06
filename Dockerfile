ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    build-base \
    sqlite-dev \
    libffi-dev \
    gcc \
    musl-dev \
    curl

# Download pre-built sqlite-vec loadable extension from GitHub releases
# Avoids musl/Alpine compilation issues with the latest source
ARG BUILD_ARCH=aarch64
RUN SQLITE_VEC_VERSION="0.1.6" \
    && case "${BUILD_ARCH}" in \
    aarch64) ARCH="linux-aarch64" ;; \
    amd64)   ARCH="linux-x86_64" ;; \
    armhf)   ARCH="linux-x86_64" ;; \
    armv7)   ARCH="linux-x86_64" ;; \
    i386)    ARCH="linux-x86_64" ;; \
    *)       ARCH="linux-x86_64" ;; \
    esac \
    && mkdir -p /usr/local/lib/sqlite-vec \
    && curl -fsSL \
    "https://github.com/asg017/sqlite-vec/releases/download/v${SQLITE_VEC_VERSION}/sqlite-vec-${SQLITE_VEC_VERSION}-loadable-${ARCH}.tar.gz" \
    | tar xz -C /usr/local/lib/sqlite-vec \
    && ls -la /usr/local/lib/sqlite-vec/

# Copy application code
COPY app /app

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

# Copy run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Persistent data directory (mapped by Supervisor)
RUN mkdir -p /data

# Set sqlite-vec extension path as env var
ENV SQLITE_VEC_PATH=/usr/local/lib/sqlite-vec/vec0

CMD ["/run.sh"]
