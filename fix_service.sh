#!/bin/bash
# Script to fix the systemd service file for QuantScope

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root or with sudo"
  exit 1
fi

# Find the actual project directory
echo "Checking for QuantScope directories..."

PROJECT_DIR=""
VENV_PATH=""

# Check common locations
possible_dirs=(
  "/root/QuantScope"
  "/root/QuantScope-1"
  "/home/ubuntu/QuantScope"
  "/home/ubuntu/QuantScope-1"
  "$(pwd)"
)

for dir in "${possible_dirs[@]}"; do
  if [ -d "$dir" ]; then
    echo "Found directory: $dir"
    
    # Check if it has the expected structure
    if [ -d "$dir/backend" ] || [ -d "$dir/venv" ]; then
      PROJECT_DIR="$dir"
      echo "This appears to be the QuantScope project directory."
      break
    fi
  fi
done

if [ -z "$PROJECT_DIR" ]; then
  echo "Could not find the QuantScope project directory."
  read -p "Please enter the full path to your QuantScope project: " PROJECT_DIR
  
  if [ ! -d "$PROJECT_DIR" ]; then
    echo "Directory does not exist: $PROJECT_DIR"
    exit 1
  fi
fi

# Check for virtual environment
echo "Checking for virtual environment..."

if [ -d "$PROJECT_DIR/venv" ]; then
  VENV_PATH="$PROJECT_DIR/venv"
  echo "Found virtual environment at: $VENV_PATH"
else
  echo "Virtual environment not found at $PROJECT_DIR/venv"
  read -p "Do you want to create a virtual environment? (y/n) [y]: " create_venv
  create_venv=${create_venv:-y}
  
  if [ "$create_venv" = "y" ]; then
    echo "Creating virtual environment..."
    cd "$PROJECT_DIR"
    python3 -m venv venv
    VENV_PATH="$PROJECT_DIR/venv"
    
    echo "Installing requirements..."
    $VENV_PATH/bin/pip install -r requirements.txt
  else
    read -p "Please enter the full path to your virtual environment: " VENV_PATH
    
    if [ ! -d "$VENV_PATH" ]; then
      echo "Directory does not exist: $VENV_PATH"
      exit 1
    fi
  fi
fi

# Check if Python executable exists
if [ ! -f "$VENV_PATH/bin/python" ]; then
  echo "Python executable not found at $VENV_PATH/bin/python"
  exit 1
fi

# Find the service file
echo "Checking for systemd service file..."

SERVICE_FILE=""
possible_services=(
  "/etc/systemd/system/quantscope.service"
  "/etc/systemd/system/quant-scope.service"
  "/etc/systemd/system/quant_scope.service"
)

for service in "${possible_services[@]}"; do
  if [ -f "$service" ]; then
    SERVICE_FILE="$service"
    echo "Found service file: $SERVICE_FILE"
    break
  fi
done

if [ -z "$SERVICE_FILE" ]; then
  echo "Could not find the systemd service file."
  read -p "Please enter the full path to your service file: " SERVICE_FILE
  
  if [ ! -f "$SERVICE_FILE" ]; then
    echo "File does not exist: $SERVICE_FILE"
    exit 1
  fi
fi

# Backup the service file
echo "Backing up service file..."
cp "$SERVICE_FILE" "${SERVICE_FILE}.bak"
echo "Backup created at ${SERVICE_FILE}.bak"

# Find the main script
echo "Looking for the main script..."

MAIN_SCRIPT=""
possible_scripts=(
  "$PROJECT_DIR/run.py"
  "$PROJECT_DIR/wsgi.py"
  "$PROJECT_DIR/app.py"
  "$PROJECT_DIR/backend/app.py"
)

for script in "${possible_scripts[@]}"; do
  if [ -f "$script" ]; then
    MAIN_SCRIPT="$script"
    echo "Found main script: $MAIN_SCRIPT"
    break
  fi
done

if [ -z "$MAIN_SCRIPT" ]; then
  echo "Could not find the main script."
  read -p "Please enter the full path to your main script: " MAIN_SCRIPT
  
  if [ ! -f "$MAIN_SCRIPT" ]; then
    echo "File does not exist: $MAIN_SCRIPT"
    exit 1
  fi
fi

# Check if using Gunicorn
echo "Checking if using Gunicorn..."

if grep -q "gunicorn" "$SERVICE_FILE"; then
  echo "Service appears to be using Gunicorn."
  USE_GUNICORN=true
else
  echo "Service appears to be using Python directly."
  USE_GUNICORN=false
fi

# Update the service file
echo "Updating service file..."

if [ "$USE_GUNICORN" = true ]; then
  # Extract the Gunicorn parameters
  GUNICORN_PARAMS=$(grep "ExecStart" "$SERVICE_FILE" | sed -E 's/.*gunicorn\s+(.+)/\1/')
  
  if [ -z "$GUNICORN_PARAMS" ]; then
    GUNICORN_PARAMS="-w 4 -b 0.0.0.0:5000 wsgi:app"
    echo "Could not extract Gunicorn parameters, using default: $GUNICORN_PARAMS"
  else
    echo "Extracted Gunicorn parameters: $GUNICORN_PARAMS"
  fi
  
  # Create a new service file
  cat > "$SERVICE_FILE" << EOL
[Unit]
Description=QuantScope Financial Risk Assessment Platform
After=network.target

[Service]
User=$(whoami)
Group=$(id -gn)
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_PATH/bin/gunicorn $GUNICORN_PARAMS
Restart=always

[Install]
WantedBy=multi-user.target
EOL
else
  # Create a new service file
  cat > "$SERVICE_FILE" << EOL
[Unit]
Description=QuantScope Financial Risk Assessment Platform
After=network.target

[Service]
User=$(whoami)
Group=$(id -gn)
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_PATH/bin/python $MAIN_SCRIPT
Restart=always

[Install]
WantedBy=multi-user.target
EOL
fi

echo "Service file updated."

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

# Restart the service
echo "Restarting the service..."
systemctl restart $(basename "$SERVICE_FILE")

# Check the status
echo "Checking service status..."
systemctl status $(basename "$SERVICE_FILE")

echo "Done."
echo "If the service is still not starting, check the logs with:"
echo "sudo journalctl -u $(basename "$SERVICE_FILE") -f"