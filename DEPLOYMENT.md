# Deployment Guide

## Prerequisites

- AWS account
- Terraform >= 1.5 installed (`brew install hashicorp/tap/terraform`)
- GitHub repository with Actions enabled
- OpenAI API key
- Slack workspace with Workflow Builder access

---

## Step 1: Slack Setup

This system uses **Slack Workflow Builder** webhooks. Messages are sent as plain text via a `payload` string variable.

For each topic channel (`#tech`, `#ai`, `#education`, `#cyber-security`):

1. Open the channel → **Integrations** → **Add a Workflow**
2. Create a workflow → trigger: **"From a webhook"**
3. In "Set up variables", add one variable named `payload` (type: text)
4. Add a **Send a message** step using the `payload` variable
5. Publish the workflow and copy the trigger URL

---

## Step 2: AWS Setup

### Terraform state bucket

Include your AWS account ID in the bucket name to ensure global uniqueness:

```bash
aws s3 mb s3://news-aggregator-terraform-state-{account-id} --region eu-west-1

aws s3api put-bucket-versioning \
  --bucket news-aggregator-terraform-state-{account-id} \
  --versioning-configuration Status=Enabled
```

### GitHub OIDC

```bash
python .github/scripts/setup-oidc.py
```

Creates an OIDC provider and IAM role so GitHub Actions can deploy to AWS without long-lived credentials. Note the role ARN output — you'll need it in Step 3.

---

## Step 3: GitHub Secrets and Variables

**Secrets** (Settings → Secrets and variables → Actions → Secrets):

| Secret | Description |
|---|---|
| `AWS_ROLE_ARN` | ARN output by setup-oidc.py |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `SLACK_WEBHOOK_TECH` | Workflow Builder URL for tech channel |
| `SLACK_WEBHOOK_AI` | Workflow Builder URL for AI channel |
| `SLACK_WEBHOOK_EDUCATION` | Workflow Builder URL for education channel |
| `SLACK_WEBHOOK_CYBER_SECURITY` | Workflow Builder URL for cyber security channel |
| `SLACK_DEPLOYMENT_WEBHOOK` | Optional — for CI/CD deploy notifications |

**Variables** (Settings → Secrets and variables → Actions → Variables):

| Variable | Value |
|---|---|
| `TF_STATE_BUCKET` | Your S3 bucket name from Step 2 |
| `DEPLOY_ENABLED` | Set to `true` to enable CD pipeline |

---

## Step 4: Deploy

### Option A: CI/CD pipeline (recommended)

Set `DEPLOY_ENABLED=true` and push to `main`. The pipeline:

1. Lint, unit test, Terraform validate
2. Build Lambda package → upload to S3
3. Deploy ephemeral test environment → run integration test → destroy
4. Deploy to production (only if tests pass, only on `main`)

All secrets and variables are injected automatically — no manual steps needed.

### Option B: Terraform CLI (manual)

The state bucket and environment are passed via `-backend-config` and `-var` so the same Terraform works for any environment:

```bash
cd infra/terraform

# Init (pass bucket and state key)
terraform init \
  -backend-config="bucket=news-aggregator-terraform-state-{account-id}" \
  -backend-config="key=prod/terraform.tfstate"

# Plan
terraform plan \
  -var-file=terraform.prod.tfvars \
  -var="environment=prod" \
  -var="openai_api_key=$OPENAI_API_KEY" \
  -var="slack_webhook_tech=$SLACK_WEBHOOK_TECH" \
  -var="slack_webhook_ai=$SLACK_WEBHOOK_AI" \
  -var="slack_webhook_education=$SLACK_WEBHOOK_EDUCATION" \
  -var="slack_webhook_cyber_security=$SLACK_WEBHOOK_CYBER_SECURITY" \
  -var="lambda_s3_bucket=news-aggregator-terraform-state-{account-id}" \
  -var="lambda_s3_key=lambda-packages/manual/lambda_function.zip"

# Apply
terraform apply -auto-approve [same vars as above]
```

**Note**: For manual deploys you need to first build and upload the Lambda package:
```bash
mkdir -p lambda_build
pip install -r requirements.txt -t lambda_build/
cp -r app config lambda_build/
cd lambda_build && zip -r ../lambda_function.zip .
aws s3 cp lambda_function.zip s3://news-aggregator-terraform-state-{account-id}/lambda-packages/manual/lambda_function.zip
```

---

## Step 5: Verify

```bash
# Lambda exists
aws lambda get-function --function-name news-aggregator-prod

# Trigger manually
aws lambda invoke \
  --function-name news-aggregator-prod \
  --payload '{}' response.json && cat response.json

# Tail logs
aws logs tail /aws/lambda/news-aggregator-prod --follow

# Check DynamoDB has articles
aws dynamodb scan --table-name news-aggregator-prod-articles --max-items 5
```

---

## Troubleshooting

**No articles being ingested**
- Check feed URLs in `config/feeds.yaml` are reachable
- Look for `Failed to fetch feed` in logs
- Verify `FEED_CONFIG_PATH=/var/task/config/feeds.yaml` is set on the Lambda

**LLM classification discarding everything**
- Check OpenAI API key is valid and has quota
- Set `ENABLE_LLM_CLASSIFICATION=false` to fall back to keywords temporarily

**Slack messages not arriving**
- Verify the webhook URL is a Workflow Builder trigger URL (`hooks.slack.com/triggers/...`)
- Check the workflow is **published** in Slack (not just saved as draft)
- Confirm the workflow variable is named exactly `payload`

**Ephemeral test environment failing in CI**
- Check CloudWatch logs for the test Lambda (`/aws/lambda/news-aggregator-test-{run-id}`)
- The destroy step always runs so no orphaned resources remain

**DynamoDB errors**
- Table name follows the pattern `news-aggregator-{environment}-articles`
- Check Lambda execution role has DynamoDB permissions

---

## Cost Estimates

### Ephemeral test environment (per CI run)
- Lambda: ~$0.00 (free tier)
- DynamoDB: ~$0.00 (PAY_PER_REQUEST, tiny volume)
- OpenAI: ~$0.01 (2 articles × 2 feeds)

**~$0.01 per CI run**

### Production (hourly runs)
- Lambda: ~$1/month
- DynamoDB: ~$1–2/month (PAY_PER_REQUEST)
- OpenAI: ~$15–30/month (classification + summarisation)
- CloudWatch: ~$1/month

**Total: ~$18–34/month**

---

## Cleanup

```bash
cd infra/terraform

terraform init \
  -backend-config="bucket=news-aggregator-terraform-state-{account-id}" \
  -backend-config="key=prod/terraform.tfstate"

terraform destroy \
  -var-file=terraform.prod.tfvars \
  -var="environment=prod" \
  -var="openai_api_key=dummy" \
  -var="lambda_s3_bucket=news-aggregator-terraform-state-{account-id}" \
  -var="lambda_s3_key=dummy"

# Remove state bucket
aws s3 rb s3://news-aggregator-terraform-state-{account-id} --force
```
