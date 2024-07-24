#!/bin/bash

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Upgrade pip
pip3 install --upgrade pip

# Install required libraries
pip3 install fastapi
pip3 install uvicorn
pip3 install psycopg2-binary
pip3 install pydantic
pip3 install numpy
pip3 install zstd
pip3 install surya-ocr
pip3 install torchaudio
pip3 install pillow
pip3 install requests
pip3 install transformers
pip3 install torch
pip3 install einops
pip3 install pycodec2
pip3 install python-dotenv
pip3 install schedule psutil caldav

# Deactivate the virtual environment
deactivate

echo "Virtual environment setup and required libraries installed."
