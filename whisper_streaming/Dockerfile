# Base image with CUDA support
FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/New_York

# Set timezone
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    build-essential \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python 3.11
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-dev

# Install CUDA libraries
RUN apt-get update && apt-get install -y \
    libcublas-12-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Create and activate virtual environment
RUN python3.11 -m venv venv
ENV PATH="/app/venv/bin:$PATH"

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port for the web app
EXPOSE 43007

# Run the server and web app
CMD ["python3.11", "whisper_server.py", \
     "--host", "0.0.0.0", \
     "--port", "43007", \
    #  "--model", "large-v3", \
    "--model", "base.en", \
     "--backend", "faster-whisper", \
    #  "--model_dir", "./faster-distil-whisper-large-v3", \
     "--silence-size", "2.0", \
     "--silence-threshold", "0.01", \
     "--min-chunk-size", "1", \
     "--task", "transcribe", \
     "--lan", "en", \
     "--vad", \
     "--buffer_trimming", "sentence", \
     "--buffer_trimming_sec", "30", \
     "--model_cache_dir", "/app/model_cache"]


# CMD ["python3.11", "whisper_online_server.py", \
#      "--host", "localhost", \
#      "--port", "43001", \
#      "--model", "large-v3", \
#      "--backend", "faster-whisper", \
#      "--model_dir", "./faster-distil-whisper-large-v3", \
#      "--silence-size", "2.0", \
#      "--silence-threshold", "0.01", \
#      "--min-chunk-size", "1", \
#      "--task", "transcribe", \
#      "--lan", "en", \
#      "--vad", \
#      "--buffer_trimming", "sentence", \
#      "--buffer_trimming_sec", "30", \
#      "--model_cache_dir", "/app/model_cache"]

# CMD ["python3.11", "whisper_online_server.py", \
#     #  "--host", "0.0.0.0", \
#     #  "--port", "43007", \
#      "--model", "large-v3", \
#      "--backend", "faster-whisper", \
#      "--model_dir", "./faster-distil-whisper-large-v3", \
#      "--min-chunk-size", "1", \
#      "--model_cache_dir", "/app/model_cache", \
#      "--task", "transcribe", \
#      "--lan", "en", \
#      "--vad", \
#      "--buffer_trimming", "sentence", \
#      "--buffer_trimming_sec", "30", \
#      "--warmup-file", "sample.wav"]
