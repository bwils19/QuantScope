#!/bin/bash
# Script to set up environment variables for the price update system

# Default values
REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_DB="0"
REDIS_PASSWORD=""
ALPHA_VANTAGE_KEY=""

# Function to prompt for a value with a default
prompt_with_default() {
  local prompt="$1"
  local default="$2"
  local var_name="$3"
  
  if [ -n "$default" ]; then
    read -p "$prompt [$default]: " value
    value=${value:-$default}
  else
    read -p "$prompt: " value
  fi
  
  eval "$var_name=\"$value\""
}

# Welcome message
echo "=== QuantScope Environment Setup ==="
echo "This script will help you set up the necessary environment variables."
echo "Press Enter to accept the default values (shown in brackets)."
echo ""

# Prompt for Redis configuration
echo "Redis Configuration:"
prompt_with_default "Redis host" "$REDIS_HOST" "REDIS_HOST"
prompt_with_default "Redis port" "$REDIS_PORT" "REDIS_PORT"
prompt_with_default "Redis database" "$REDIS_DB" "REDIS_DB"
read -p "Redis password (leave empty if none): " REDIS_PASSWORD

# Construct Redis URL
if [ -n "$REDIS_PASSWORD" ]; then
  REDIS_URL="redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}"
else
  REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}"
fi

# Prompt for Alpha Vantage API key
echo ""
echo "Alpha Vantage API Key:"
read -p "Enter your Alpha Vantage API key: " ALPHA_VANTAGE_KEY

# Check if .env file exists
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
  echo ""
  echo "Existing .env file found."
  read -p "Do you want to update it? (y/n) [y]: " update_env
  update_env=${update_env:-y}
  
  if [ "$update_env" != "y" ]; then
    echo "Exiting without changes."
    exit 0
  fi
  
  # Backup existing .env file
  cp "$ENV_FILE" "${ENV_FILE}.bak"
  echo "Backed up existing .env file to ${ENV_FILE}.bak"
fi

# Update or create .env file
echo ""
echo "Writing environment variables to $ENV_FILE..."

# Function to update or add a variable to .env file
update_env_var() {
  local var_name="$1"
  local var_value="$2"
  
  if grep -q "^${var_name}=" "$ENV_FILE" 2>/dev/null; then
    # Variable exists, update it
    sed -i "s|^${var_name}=.*|${var_name}=${var_value}|" "$ENV_FILE"
  else
    # Variable doesn't exist, add it
    echo "${var_name}=${var_value}" >> "$ENV_FILE"
  fi
}

# Update or create the .env file
update_env_var "REDIS_URL" "$REDIS_URL"
update_env_var "ALPHA_VANTAGE_KEY" "$ALPHA_VANTAGE_KEY"

echo "Environment variables have been set up successfully."
echo ""
echo "Redis URL: $REDIS_URL"
echo "Alpha Vantage API Key: ${ALPHA_VANTAGE_KEY:0:5}... (truncated for security)"
echo ""
echo "To apply these changes, you need to restart your Flask application and Celery services."