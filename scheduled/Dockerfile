# Stage 1: Build
FROM python:3.11-slim as build

WORKDIR /app

COPY scheduled/requirements.txt .
COPY libraries/db/requirements.txt ./db_requirements.txt
COPY libraries/gotify/requirements.txt ./gotify_requirements.txt

RUN apt-get update && apt-get install -y build-essential && \
    python3 -m venv venv && \
    . venv/bin/activate && \
    pip install --upgrade pip && \
    pip install wheel && \
    pip install --no-cache-dir -r requirements.txt -r db_requirements.txt -r gotify_requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

COPY --from=build /app/venv /app/venv
# COPY scheduled ./scheduled
COPY libraries/db ./libraries/db
COPY libraries/gotify ./libraries/gotify
# COPY main.py .

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright
RUN . venv/bin/activate && \
    pip install playwright && \
    playwright install chromium

# Install additional fonts (optional, but can be helpful)
RUN apt-get update && apt-get install -y \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*


ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/libraries:$PYTHONPATH"

WORKDIR /app/scheduled
CMD ["python3.11", "main.py"]