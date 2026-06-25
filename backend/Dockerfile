FROM python:3.12-slim AS base

# System dependencies for Playwright.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium.
RUN playwright install --with-deps chromium

# Copy application code.
COPY . .

# Create data directories.
RUN mkdir -p data/pdf data/uploads

EXPOSE 8000

# Default command, overridden per service in compose.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
