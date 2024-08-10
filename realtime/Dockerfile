# Stage 1: Build
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04 as build

WORKDIR /app

# Set timezone
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python 3.11 and tzdata
RUN apt-get update && apt-get install -y software-properties-common tzdata && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-dev

COPY realtime/requirements.txt .
COPY libraries/db/requirements.txt ./db_requirements.txt
COPY libraries/gotify/requirements.txt ./gotify_requirements.txt
COPY libraries/embed/requirements.txt ./embed_requirements.txt
# COPY libraries/llm/requirements.txt ./llm_requirements.txt

RUN python3.11 -m venv venv && \
    . venv/bin/activate && \
    pip install --upgrade pip && \
    pip install wheel && \
    pip install --no-cache-dir -r requirements.txt -r db_requirements.txt -r gotify_requirements.txt -r embed_requirements.txt
    #  -r llm_requirements.txt

# Stage 2: Runtime
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

WORKDIR /app

# Set timezone
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install Python 3.11 and tzdata
RUN apt-get update && apt-get install -y software-properties-common tzdata && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-venv

COPY --from=build /app/venv /app/venv
COPY libraries/db ./libraries/db
COPY libraries/gotify ./libraries/gotify
COPY libraries/embed ./libraries/embed
COPY libraries/llm ./libraries/llm

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/libraries:$PYTHONPATH"

# $REALTIME_SERVER_PORT
EXPOSE 8081

WORKDIR /app/realtime
CMD ["python3.11", "main.py"]