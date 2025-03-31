#!/bin/bash
# Script to clear the risk analysis cache on the server

# Connect to the database and clear the cache
echo "DELETE FROM risk_analysis_cache;" | sqlite3 /path/to/your/database.db

# Restart the application
sudo systemctl restart quantscope.service

echo "Cache cleared and application restarted"
