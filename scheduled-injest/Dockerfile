FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY libraries/db/requirements.txt ./db_requirements.txt
COPY libraries/gotify/requirements.txt ./gotify_requirements.txt

RUN python3 -m venv venv && \
    . venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt -r db_requirements.txt -r gotify_requirements.txt

COPY . .
COPY libraries/db ./library/db
COPY libraries/gotify ./library/gotify

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/library:$PYTHONPATH"

CMD ["python3", "scheduled-injest.py"]