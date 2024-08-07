# Stage 1: Build
FROM python:3.11-slim as build

WORKDIR /app

COPY subscriptions/requirements.txt .
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
# COPY .env ./subscriptions/.env

# COPY subscriptions ./subscriptions
COPY libraries/db ./libraries/db
COPY libraries/gotify ./libraries/gotify

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/libraries:$PYTHONPATH"

WORKDIR /app/subscriptions
CMD ["python3.11", "main.py"]