# Use official Microsoft Playwright Python base image with all browser libraries pre-installed
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc and buffer stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HEADLESS=true
ENV PORT=8000

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure Playwright browser binaries are present
RUN playwright install chromium

# Copy application source code
COPY . .

# Expose Render PORT
EXPOSE 8000

# Run FastAPI app with dynamic port binding for Render
CMD uvicorn src.web.app:app --host 0.0.0.0 --port ${PORT:-8000}

