#!/bin/bash

echo "Basic dependencies installation - probably will break on anything but popos"
echo "Based on https://support.system76.com/articles/cuda/"

# Update and upgrade system packages
sudo apt update && sudo apt full-upgrade -y

# Install required packages
sudo apt install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common

# Install NVIDIA drivers and CUDA
sudo apt install -y nvidia-driver-535 nvidia-cuda-toolkit

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt update && sudo apt install -y nvidia-container-toolkit

# Configure Docker to use NVIDIA Container Toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Add current user to docker group
sudo usermod -aG docker $USER

# Add kernel parameter for cgroup hierarchy
sudo kernelstub --add-options "systemd.unified_cgroup_hierarchy=0"

echo "Setup complete. Please reboot your system for changes to take effect."
read -p "Press Enter to continue after you have rebooted your system..."

# Verify Docker installation
if ! command -v docker &> /dev/null
then
    echo "Docker is not installed or not in PATH. Please check the installation."
    exit 1
fi

# Verify NVIDIA drivers and CUDA installation
if ! nvidia-smi &> /dev/null
then
    echo "NVIDIA drivers or CUDA is not installed properly. Please check the installation."
    exit 1
fi

# Verify Docker Compose installation
if ! docker-compose --version &> /dev/null
then
    echo "Docker Compose is not installed or not in PATH. Please check the installation."
    exit 1
fi

# Verify NVIDIA Container Toolkit
if ! docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi &> /dev/null
then
    echo "NVIDIA Container Toolkit is not working properly. Please check the installation."
    exit 1
fi

echo "All dependencies are installed and working correctly."

echo "System is ready for use."

# Bring up the Docker containers defined in docker-compose.yml
echo "Starting Docker containers..."
sudo docker-compose up --remove-orphans --force-recreate --build

# Check the health of specific Docker containers defined in docker-compose.yml
echo "Checking health of Docker containers..."
containers=("timescaledb-pino" "gotify-pino" "subscriptions-pino" "scheduled-pino" "realtime-pino")
timeout=300
start_time=$(date +%s)

while true; do
    unhealthy_containers=0
    
    for container in "${containers[@]}"; do
        status=$(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null)
        if [ "$status" != "healthy" ]; then
            unhealthy_containers=$((unhealthy_containers + 1))
            echo "$container: $status"
        fi
    done
    
    if [ $unhealthy_containers -eq 0 ]; then
        echo "All specified containers are healthy!"
        break
    fi

    current_time=$(date +%s)
    elapsed=$((current_time - start_time))
    
    if [ $elapsed -ge $timeout ]; then
        echo "Timeout reached. Some containers may not be healthy."
        for container in "${containers[@]}"; do
            echo "$container: $(docker inspect --format='{{.State.Health.Status}}' $container 2>/dev/null)"
        done
        exit 1
    fi

    echo "Waiting for containers to be healthy... ($elapsed seconds elapsed)"
    sleep 10
done

echo "All specified Docker containers are up and healthy."


