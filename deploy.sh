#!/bin/bash

# Google Cloud Run deployment script
# Usage: ./deploy.sh [PROJECT_ID]

set -e

PROJECT_ID=${1:-$(gcloud config get-value project)}
SERVICE_NAME="meeting-translate"
REGION="us-central1"

if [ -z "$PROJECT_ID" ]; then
    echo "Error: PROJECT_ID not specified and no default project configured"
    echo "Usage: $0 [PROJECT_ID]"
    exit 1
fi

echo "Deploying to project: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"

# Build and deploy using Cloud Build
gcloud builds submit --config cloudbuild.yaml --project $PROJECT_ID

# Get the service URL
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)" --project=$PROJECT_ID)

echo ""
echo "🎉 Deployment complete!"
echo "Service URL: $SERVICE_URL"
echo ""
echo "Update your Chrome extension's offscreen.js with:"
echo "const wsUrl = \"wss://${SERVICE_URL#https://}/stream\";"
echo ""
echo "Don't forget to:"
echo "1. Enable the Speech-to-Text API in your Google Cloud project"
echo "2. Ensure your Cloud Run service has the necessary permissions"