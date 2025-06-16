#!/bin/bash

prompt_if_empty() {
    local var_name=$1
    local prompt_text=$2
    local default_value=$3

    read -p "$prompt_text [$default_value]: " input
    input="${input:-$default_value}"
    eval "$var_name=\"$input\""
}

echo "🛠️ Google Cloud Service Account Setup Script"

prompt_if_empty PROJECT_ID "Enter your GCP Project ID" "my-gcp-project"
prompt_if_empty SA_NAME "Enter the Service Account name (short name)" "my-automated-sa"
prompt_if_empty SA_DISPLAY_NAME "Enter a display name for the Service Account" "My Automated Service Account"

SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "🔧 Setting project to ${PROJECT_ID}..."
gcloud config set project "${PROJECT_ID}"

echo "👤 Creating service account: ${SA_EMAIL}..."
gcloud iam service-accounts create "${SA_NAME}" \
    --display-name="${SA_DISPLAY_NAME}" || echo "⚠️  Service account may already exist."

echo "🔑 Creating key and saving to credentials.json..."
gcloud iam service-accounts keys create "credentials.json" \
    --iam-account="${SA_EMAIL}"

echo -e "\n✅ Done!"
echo "📁 Service account key saved to: credentials.json"
echo "📌 You may now use this key to authenticate with the Google Sheets API or share your sheet with this email: ${SA_EMAIL}"

