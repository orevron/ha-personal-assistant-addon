ARG BUILD_FROM
FROM $BUILD_FROM

# Install system dependencies for sqlite-vec native extension and Python
RUN apk add --no-cache \
    python3 \
    py3-pip \
    build-base \
    sqlite-dev \
    libffi-dev \
    gcc \
    musl-dev

# Copy application code
COPY app /app

# Install Python dependencies in isolated mode
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

# Copy run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Persistent data directory (mapped by Supervisor)
RUN mkdir -p /data

CMD ["/run.sh"]
