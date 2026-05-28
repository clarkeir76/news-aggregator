# Deployment Guide

## Prerequisites

- AWS account with permissions to create Lambda, DynamoDB, EventBridge, IAM, S3, Secrets Manager
- Terraform >= 1.0 installed
- GitHub repository with Actions enabled
- OpenAI API key
- Slack workspace with Workflow Builder access

---

## Step 1: Slack Setup

This system uses **Slack Workflow Builder** webhooks — not traditional incoming webhooks.

For each topic channel (`#tech`, `#ai`, `#education`, `#cyber-security`):

1. Open the channel in Slack → click the channel name → **Integrations** → **Add a Workflow**
2. Create a new workflow → choose **"From a webhook"** as the trigger
3. In "Set up variables", add one variable named `payload` (type: text)
4. Add a **Send a message** step that uses the `payload` variable as the message body
5. Publish the workflow
6. Copy the webhook trigger URL

You'll end up with four URLs:
```
SLACK_WEBHOOK_TECH=https://hooks.slack.com/triggers/...
SLACK_WEBHOOK_AI=https://hooks.slack.com/triggers/...
SLACK_WEBHOOK_EDUCATION=https://hooks.slack.com/triggers/...
SLACK_WEBHOOK_CYBER_SECURITY=https://hooks.slack.com/triggers/...
```

---

## Step 2: AWS Setup

### Terraform state bucket

```bash
aws s3 mb s3://news-aggregator-terraform-state

aws s3api put-bucket-versioning \
  --bucket news-aggregator-terraform-state \
  --versioning-configuration Status=Enabled
```

### GitHub OIDC (for CI/CD)

```bash
cd .github/scripts
python setup-oidc.py
```

This creates an OIDC provider and an IAM role that GitHub Actions assumes. No long-lived credentials needed.

---

## Step 3: GitHub Secrets

Add these secrets to your GitHub repository (**Settings → Secrets and variables → Actions**):

| Secret | Description |
|---|---|
| `AWS_ROLE_ARN` | ARN of the IAM role created by setup-oidc.py |
| `OPENAI_API_KEY` | Your OpenAI API key |
| `SLACK_WEBHOOK_TECH` | Workflow Builder URL for tech channel |
| `SLACK_WEBHOOK_AI` | Workflow Builder URL for AI channel |
| `SLACK_WEBHOOK_EDUCATION` | Workflow Builder URL for education channel |
| `SLACK_WEBHOOK_CYBER_SECURITY` | Workflow Builder URL for cyber security channel |
| `SLACK_DEPLOYMENT_WEBHOOK` | Optional — webhook for CI/CD deploy notifications |

---

## Step 4: Deploy Infrastructure

### Option A: Terraform CLI

```bash
cd infra/terraform

terraform init

# Review what will be created
terraform plan -var-file=terraform.dev.tfvars

# Deploy
terraform apply -var-file=terraform.dev.tfvars
```

For production:
```bash
terraform apply \
  -var-file=terraform.prod.tfvars \
  -var="openai_api_key=$OPENAI_API_KEY" \
  -var="slack_webhook_tech=$SLACK_WEBHOOK_TECH" \
  -var="slack_webhook_ai=$SLACK_WEBHOOK_AI" \
  -var="slack_webhook_education=$SLACK_WEBHOOK_EDUCATION" \
  -var="slack_webhook_cyber_security=$SLACK_WEBHOOK_CYBER_SECURITY"
```

### Option B: GitHub Actions (automated)

Push to `main` — the pipeline handles everything:
1. Lint and test
2. Terraform validate and plan
3. Terraform apply
4. Lambda deploy

---

## Step 5: Lambda Environment Variables

After deploying via Terraform, set the following environment variables on the Lambda function (either via Terraform variables or the AWS console):

```
AWS_REGION=eu-west-1
DYNAMODB_TABLE=news-articles
OPENAI_API_KEY=<from Secrets Manager>
OPENAI_MODEL=gpt-4o-mini
ENABLE_SLACK=true
ENABLE_SUMMARIZATION=true
ENABLE_PERSISTENCE=true
ENABLE_LLM_CLASSIFICATION=true
FEED_CONFIG_PATH=/opt/config/feeds.yaml
LOG_LEVEL=INFO
MAX_ARTICLES_PER_FEED=50
MAX_CONCURRENT_FEEDS=10
MAX_CONCURRENT_SUMMARIZATIONS=5
MAX_ARTICLE_AGE_HOURS=24
LAST_RUN_FILE=/tmp/.last_run
SLACK_WEBHOOK_TECH=<from Secrets Manager>
SLACK_WEBHOOK_AI=<from Secrets Manager>
SLACK_WEBHOOK_EDUCATION=<from Secrets Manager>
SLACK_WEBHOOK_CYBER_SECURITY=<from Secrets Manager>
```

Note: `FEED_CONFIG_PATH` must be set to `/opt/config/feeds.yaml` in Lambda. This is where the build packages `config/feeds.yaml`.

---

## Step 6: Verify Deployment

```bash
# Check Lambda exists
aws lambda get-function --function-name news-aggregator

# Manually trigger a run
aws lambda invoke \
  --function-name news-aggregator \
  --payload '{}' \
  response.json && cat response.json

# Tail logs
aws logs tail /aws/lambda/news-aggregator --follow

# Check for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/news-aggregator \
  --filter-pattern "ERROR"

# Check articles are being stored
aws dynamodb scan --table-name news-articles --max-items 5
```

---

## Troubleshooting

**No articles being ingested**
- Check that feed URLs in `config/feeds.yaml` are reachable
- Look for `Failed to fetch feed` in logs
- Verify `FEED_CONFIG_PATH` points to the right location

**LLM classification discarding everything**
- Check OpenAI API key is valid and has quota
- Set `ENABLE_LLM_CLASSIFICATION=false` to fall back to keyword matching temporarily
- Check logs for `LLM classification failed`

**Slack messages not arriving**
- Verify the webhook URL is a Workflow Builder trigger URL (`hooks.slack.com/triggers/...`)
- Check the workflow is **published** in Slack (not just saved as draft)
- Confirm the workflow has a variable named exactly `payload`
- Check logs for `Slack webhook returned`

**Lambda timeout**
- Reduce `MAX_ARTICLES_PER_FEED` or `MAX_CONCURRENT_FEEDS`
- Increase Lambda timeout in Terraform (currently 5 minutes)
- Check if a specific feed is hanging (look for feeds with no completion log)

**DynamoDB errors**
- Check `DYNAMODB_TABLE` matches the deployed table name
- Verify the Lambda execution role has `dynamodb:PutItem`, `dynamodb:GetItem`, `dynamodb:UpdateItem`, `dynamodb:Query`, `dynamodb:Scan` permissions

---

## Cost Estimates

### Development (daily runs, 5 articles/feed)
- Lambda: ~$0.00 (free tier)
- DynamoDB: ~$0.50/month
- OpenAI: ~$1–3/month
- CloudWatch: ~$0.50/month

**Total: ~$2–4/month**

### Production (hourly runs, 50 articles/feed)
- Lambda: ~$1/month
- DynamoDB: ~$2–5/month
- OpenAI: ~$15–30/month (classification + summarisation)
- CloudWatch: ~$1/month

**Total: ~$20–40/month**

---

## Updating Feeds

To add or remove RSS feeds, edit `config/feeds.yaml` and push to `main`. The CI/CD pipeline repackages the Lambda with the updated feeds file.

---

## Cleanup

```bash
cd infra/terraform
terraform destroy -var-file=terraform.prod.tfvars

# Remove state bucket
aws s3 rb s3://news-aggregator-terraform-state --force
```
