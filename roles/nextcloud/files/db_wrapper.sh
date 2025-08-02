#!/bin/bash

# Export environment variables if needed
export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB

echo "[INFO] Starting PostgreSQL in background..."
docker-entrypoint.sh postgres &

# Wait until PostgreSQL is ready
echo "[INFO] Waiting for PostgreSQL to become available..."
until pg_isready -U "$POSTGRES_USER"; do
  sleep 2
done

echo "[INFO] PostgreSQL is ready. Executing custom SQL script..."

# Run your custom SQL script
psql -U "$POSTGRES_USER" -d postgres -f /custom-init/init-multiple-db.sql
if [ $? -ne 0 ]; then
  echo "[ERROR] SQL script execution failed." >&2
  exit 1
else
  echo "[INFO] SQL script executed successfully."
fi

# Wait for the PostgreSQL process to finish
wait
