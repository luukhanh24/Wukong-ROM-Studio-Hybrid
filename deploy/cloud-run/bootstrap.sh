#!/usr/bin/env bash
set -euo pipefail

project_id="${PROJECT_ID:-wukong-rom-studio-1678823419}"
region="${REGION:-asia-southeast1}"
github_repository="${GITHUB_REPOSITORY:-luukhanh24/Wukong-ROM-Studio-Hybrid}"
service="${CLOUD_RUN_SERVICE:-wukong-mini-api}"
artifact_repository="${ARTIFACT_REPOSITORY:-wukong}"
pool="github"
provider="wukong-main"

if ! gcloud projects describe "$project_id" >/dev/null 2>&1; then
  gcloud projects create "$project_id" --name="Wukong ROM Studio"
fi
gcloud config set project "$project_id" >/dev/null
if [[ -n "${BILLING_ACCOUNT_ID:-}" ]]; then
  gcloud billing projects link "$project_id" --billing-account="$BILLING_ACCOUNT_ID"
fi
gcloud billing projects describe "$project_id" --format='value(billingEnabled)' | grep -qx True || {
  echo "Link an active billing account, then rerun this script." >&2
  exit 2
}

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudtasks.googleapis.com \
  billingbudgets.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com

if ! gcloud artifacts repositories describe "$artifact_repository" --location="$region" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$artifact_repository" \
    --repository-format=docker \
    --location="$region" \
    --description="Wukong Cloud Run release images"
fi
gcloud artifacts repositories set-cleanup-policies "$artifact_repository" \
  --location="$region" \
  --policy="deploy/cloud-run/artifact-cleanup-policy.json" \
  --no-dry-run

for account in github-cloud-run-deployer wukong-runtime wukong-tasks; do
  if ! gcloud iam service-accounts describe "$account@$project_id.iam.gserviceaccount.com" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$account" --display-name="$account"
  fi
done
deployer="github-cloud-run-deployer@$project_id.iam.gserviceaccount.com"
runtime="wukong-runtime@$project_id.iam.gserviceaccount.com"
tasks="wukong-tasks@$project_id.iam.gserviceaccount.com"

for role in roles/run.admin roles/artifactregistry.writer roles/cloudtasks.enqueuer; do
  gcloud projects add-iam-policy-binding "$project_id" \
    --member="serviceAccount:$deployer" --role="$role" --condition=None >/dev/null
done
for role in roles/secretmanager.secretAccessor roles/cloudtasks.enqueuer; do
  gcloud projects add-iam-policy-binding "$project_id" \
    --member="serviceAccount:$runtime" --role="$role" --condition=None >/dev/null
done
for caller in "$deployer" "$runtime"; do
  gcloud iam service-accounts add-iam-policy-binding "$tasks" \
    --member="serviceAccount:$caller" \
    --role=roles/iam.serviceAccountUser >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$runtime" \
  --member="serviceAccount:$deployer" \
  --role=roles/iam.serviceAccountUser >/dev/null

for queue in wukong-telegram wukong-dispatch; do
  if ! gcloud tasks queues describe "$queue" --location="$region" >/dev/null 2>&1; then
    gcloud tasks queues create "$queue" --location="$region"
  fi
done
gcloud tasks queues update wukong-telegram --location="$region" \
  --max-concurrent-dispatches=10 --max-attempts=12 \
  --min-backoff=5s --max-backoff=300s --max-doublings=5
gcloud tasks queues update wukong-dispatch --location="$region" \
  --max-concurrent-dispatches=2 --max-attempts=12 \
  --min-backoff=10s --max-backoff=600s --max-doublings=5

for secret in \
  wukong-database-url \
  wukong-telegram-bot-token \
  wukong-github-token \
  wukong-rclone-config \
  wukong-actions-callback-secret; do
  if ! gcloud secrets describe "$secret" >/dev/null 2>&1; then
    gcloud secrets create "$secret" --replication-policy=automatic
  fi
done

if ! gcloud iam workload-identity-pools describe "$pool" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$pool" \
    --location=global --display-name="GitHub Actions"
fi
if ! gcloud iam workload-identity-pools providers describe "$provider" \
  --workload-identity-pool="$pool" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$provider" \
    --workload-identity-pool="$pool" \
    --location=global \
    --issuer-uri=https://token.actions.githubusercontent.com \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='$github_repository' && assertion.sub=='repo:$github_repository:environment:cloud-run-production'"
fi
project_number="$(gcloud projects describe "$project_id" --format='value(projectNumber)')"
provider_resource="projects/$project_number/locations/global/workloadIdentityPools/$pool/providers/$provider"
principal="principalSet://iam.googleapis.com/projects/$project_number/locations/global/workloadIdentityPools/$pool/attribute.repository/$github_repository"
gcloud iam service-accounts add-iam-policy-binding "$deployer" \
  --member="$principal" --role=roles/iam.workloadIdentityUser >/dev/null

if ! gcloud run services describe "$service" --region="$region" >/dev/null 2>&1; then
  gcloud run deploy "$service" \
    --image=us-docker.pkg.dev/cloudrun/container/hello \
    --region="$region" \
    --service-account="$runtime" \
    --allow-unauthenticated \
    --quiet
fi
api_url="$(gcloud run services describe "$service" --region="$region" --format='value(status.url)')"
gcloud run services add-iam-policy-binding "$service" --region="$region" \
  --member="serviceAccount:$tasks" --role=roles/run.invoker >/dev/null

if [[ -n "${BILLING_ACCOUNT_ID:-}" ]]; then
  if ! gcloud billing budgets list --billing-account="$BILLING_ACCOUNT_ID" \
    --filter="displayName=Wukong Cloud Run" --format='value(name)' | grep -q .; then
    gcloud billing budgets create \
      --billing-account="$BILLING_ACCOUNT_ID" \
      --display-name="Wukong Cloud Run" \
      --budget-amount=5USD \
      --filter-projects="projects/$project_number" \
      --threshold-rule=percent=0.2 \
      --threshold-rule=percent=1.0
  fi
fi

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh variable set GCP_PROJECT_ID --repo "$github_repository" --body "$project_id"
  gh variable set WUKONG_CLOUD_RUN_API_URL --repo "$github_repository" --body "$api_url"
  gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "$github_repository" --body "$provider_resource"
  gh secret set GCP_DEPLOYER_SERVICE_ACCOUNT --repo "$github_repository" --body "$deployer"
fi

cat <<EOF
Cloud Run bootstrap is ready.

Project: $project_id
Region: $region
API URL: $api_url
Workload Identity Provider: $provider_resource
Deployer: $deployer
Runtime: $runtime
Task identity: $tasks

Add each secret version without printing it, for example:
  printf '%s' "\$DATABASE_URL" | gcloud secrets versions add wukong-database-url --data-file=-

Required secret mapping:
  DATABASE_URL                     -> wukong-database-url
  WUKONG_TELEGRAM_BOT_TOKEN        -> wukong-telegram-bot-token
  WUKONG_GITHUB_TOKEN              -> wukong-github-token
  decoded rclone.conf              -> wukong-rclone-config
  WUKONG_ACTIONS_CALLBACK_SECRET   -> wukong-actions-callback-secret

The WUKONG_ACTIONS_CALLBACK_SECRET value must also be stored as the GitHub
Actions secret with the same name so progress and terminal callbacks share one
HMAC key.

If GitHub CLI was not authenticated, configure these repository values manually:
  variable GCP_PROJECT_ID=$project_id
  variable WUKONG_CLOUD_RUN_API_URL=$api_url
  secret GCP_WORKLOAD_IDENTITY_PROVIDER=$provider_resource
  secret GCP_DEPLOYER_SERVICE_ACCOUNT=$deployer
  secret WUKONG_ACTIONS_CALLBACK_SECRET=<same value as GCP Secret Manager>
EOF
