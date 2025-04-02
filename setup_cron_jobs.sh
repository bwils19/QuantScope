#!/bin/bash
# Script to set up cron jobs for price updates
# This is an alternative to using systemd services

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root or with sudo"
  exit 1
fi

# Get the username to run the cron jobs as
if [ -z "$1" ]; then
  echo "Usage: $0 <username>"
  echo "Example: $0 ubuntu"
  exit 1
fi

USERNAME=$1
PROJECT_DIR=$(pwd)
VENV_PATH="$PROJECT_DIR/venv"

# Check if the virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
  echo "Virtual environment not found at $VENV_PATH"
  echo "Please create a virtual environment first"
  exit 1
fi

# Create log directory
LOG_DIR="/var/log/quant_scope"
mkdir -p $LOG_DIR
chown $USERNAME:$USERNAME $LOG_DIR

# Create the cron job file
CRON_FILE="/tmp/quant_scope_cron"
cat > $CRON_FILE << EOL
# QuantScope price update cron jobs
# Update prices every 30 minutes during market hours (9:30 AM - 4:00 PM ET, weekdays)
*/30 9-16 * * 1-5 cd $PROJECT_DIR && $VENV_PATH/bin/python update_prices.py --task prices >> $LOG_DIR/price_update.log 2>&1

# Save closing prices at market close (4:00 PM ET, weekdays)
0 16 * * 1-5 cd $PROJECT_DIR && $VENV_PATH/bin/python update_prices.py --task closing >> $LOG_DIR/closing_prices.log 2>&1

# Update historical data after market close (4:30 PM ET, weekdays)
30 16 * * 1-5 cd $PROJECT_DIR && $VENV_PATH/bin/python update_prices.py --task historical >> $LOG_DIR/historical_data.log 2>&1

# Run a health check every hour to make sure everything is working
0 * * * * cd $PROJECT_DIR && $VENV_PATH/bin/python check_price_updates.py --days 1 >> $LOG_DIR/health_check.log 2>&1
EOL

# Install the cron job for the specified user
crontab -u $USERNAME $CRON_FILE
rm $CRON_FILE

echo "Cron jobs installed for user $USERNAME"
echo "Logs will be written to $LOG_DIR"
echo "To view the installed cron jobs, run: crontab -l -u $USERNAME"