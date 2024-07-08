#!/bin/bash

# source scrape-env/bin/activate


# Step 1: Install Homebrew (if not already installed)
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v brew &>/dev/null; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi

    # Step 2: Install Python 3 (if not already installed)
    if ! command -v python3.11 &>/dev/null; then
        echo "Installing Python 3.11.."
        brew install python@3.11
    fi
fi

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if [ -f /etc/debian_version ]; then
        echo "Detected Debian-based distribution. Installing postgresql-16 and libpq-dev..."
        sudo sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list'
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
        sudo apt update
        sudo apt install -y postgresql-16 postgresql-contrib-16^C
        sudo apt install -y libpq-dev
        sudo apt-get install -y libevent-2.1-7 

        echo "Installing Python 3.11..."
        sudo apt install -y python3.11 python3.11-venv python3.11-dev
    fi
fi


# Step 3: Create a virtual environment
echo "Creating virtual environment..."
python3.11 -m venv scrape-env

# Step 4: Activate the virtual environment
echo "Activating virtual environment..."
source scrape-env/bin/activate

# Step 5: Install required packages from requirements.txt
pip install --upgrade pip
pip install -r requirements.txt

playwright install

# Step 6: Done
echo "Setup complete. You are now using the virtual environment."
