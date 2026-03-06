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
    git \
    gettext

# Build sqlite-vec from source as a loadable extension
# gettext provides envsubst which the Makefile needs to generate sqlite-vec.h
RUN cd /tmp \
    && git clone --depth 1 https://github.com/asg017/sqlite-vec.git \
    && cd sqlite-vec \
    && make loadable \
    && mkdir -p /usr/local/lib/sqlite-vec \
    && cp dist/vec0.so /usr/local/lib/sqlite-vec/ \
    && cd / \
    && rm -rf /tmp/sqlite-vec

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
