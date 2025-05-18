#!/bin/bash

echo "Pulling changes"
git pull origin main

echo "Rebuilding Docker image"
docker compose build

echo "Restarting FastAPI container"
docker compose down
docker compose up -d

echo "✅ Deployed!"
