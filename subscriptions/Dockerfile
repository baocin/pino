FROM python:3.11-slim

WORKDIR /app

COPY subscriptions/requirements.txt .
COPY libraries/db/requirements.txt ./db_requirements.txt
COPY libraries/gotify/requirements.txt ./gotify_requirements.txt

RUN python3 -m venv venv && \
    . venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt -r db_requirements.txt -r gotify_requirements.txt

COPY subscriptions ./subscriptions
COPY libraries/db ./libraries/db
COPY libraries/gotify ./libraries/gotify

ENV PATH="/app/venv/bin:$PATH"

CMD ["python", "subscriptions/main.py"]