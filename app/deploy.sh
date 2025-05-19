#!/bin/bash

echo "Pulling Changes from GitHub"
git pull origin main

echo "Rebuilding Docker Image and Restarting FastAPI Container"
docker-compose down
docker-compose up -d --build

echo "✅ Deployed!"
