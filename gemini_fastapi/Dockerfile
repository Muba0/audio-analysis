# Base image
FROM python:3.11-slim as base

# Set the working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install system-level dependencies (including procps for pgrep)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmp3lame-dev \
    procps \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Clean up unnecessary files
RUN rm requirements.txt

# Web service
FROM base as web

# Copy specific files for the web service
COPY app.py apimanager.py templates/ static/ ./ 

# Expose port for the web application
EXPOSE 8000

# Command to run the web server with multiple workers for concurrency
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--timeout-keep-alive", "120"]

# Worker service
FROM base as worker

# Copy specific files for the worker
COPY tasks.py transcription.py ./ 

# Generate a unique worker name using hostname and random suffix
ENV CELERY_WORKER_NAME=worker@${HOSTNAME}

# Command to run Celery worker with unique name
CMD celery -A tasks worker --loglevel=info -n ${CELERY_WORKER_NAME} --concurrency=4

# Scaler service
FROM base as scaler

# Environment variables for scaler configuration
ENV MIN_WORKERS=3 \
    MAX_WORKERS=20 \
    TASKS_PER_WORKER=1 \
    CHECK_INTERVAL=10 \
    SCALE_UP_THRESHOLD=0.8 \
    SCALE_DOWN_THRESHOLD=0.3 \
    COOLDOWN_PERIOD=60 \
    WORKER_STARTUP_TIME=30 \
    WORKER_PREFIX=celery_worker

# Command to run the scaler script
CMD ["python", "scaler.py"]

# Nginx service
FROM nginx:alpine as nginx

# Remove default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx/conf/default.conf /etc/nginx/conf.d/

# Copy static files
COPY static /usr/share/nginx/html/static/

# Create uploads directory
RUN mkdir -p /usr/share/nginx/html/uploads && \
    chmod 777 /usr/share/nginx/html/uploads

# Expose ports
EXPOSE 80 443

# Default command
CMD ["nginx", "-g", "daemon off;"]