# Deployment Guide

## Pre-deployment Checklist

- [ ] AWS Account with appropriate permissions
- [ ] GitHub repository created and pushed
- [ ] Terraform state S3 bucket created
- [ ] OpenAI API key obtained
- [ ] Slack workspace access and webhook URLs created
- [ ] GitHub OIDC setup completed

## Step 1: AWS Setup

### Create Terraform State Bucket

```bash
# Create S3 bucket for state
aws s3 mb s3://news-aggregator-terraform-state

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket news-aggregator-terraform-state \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket news-aggregator-terraform-state \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Create DynamoDB table for locks
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

### Setup GitHub OIDC

```bash
# Run the setup script
cd .github/scripts
python setup-oidc.py
```

This will:
1. Create an OIDC provider
2. Create an IAM role for GitHub Actions
3. Attach necessary policies

## Step 2: Slack Setup

### Create Slack Webhooks

1. Go to https://api.slack.com/apps
2. Create New App → From scratch
3. For each topic (tech, ai, education, cyber_security):
   - Go to "Incoming Webhooks"
   - Create New Webhook to Channel
   - Copy the webhook URL
   - Save it securely

## Step 3: GitHub Secrets

Add the following secrets to your GitHub repository:

```
AWS_ROLE_ARN
OPENAI_API_KEY
SLACK_WEBHOOK_TECH
SLACK_WEBHOOK_AI
SLACK_WEBHOOK_EDUCATION
SLACK_WEBHOOK_CYBER_SECURITY
```

## Step 4: Deploy Infrastructure

### Option A: Terraform CLI (Manual)

```bash
cd infra/terraform

# Initialize
terraform init

# Review plan (dev)
terraform plan -var-file=terraform.dev.tfvars

# Deploy (dev)
terraform apply -var-file=terraform.dev.tfvars

# Deploy (prod)
terraform apply \
  -var-file=terraform.prod.tfvars \
  -var="openai_api_key=$(echo $OPENAI_API_KEY | base64 -d)" \
  -var="slack_webhook_tech=$SLACK_WEBHOOK_TECH" \
  -var="slack_webhook_ai=$SLACK_WEBHOOK_AI" \
  -var="slack_webhook_education=$SLACK_WEBHOOK_EDUCATION" \
  -var="slack_webhook_cyber_security=$SLACK_WEBHOOK_CYBER_SECURITY"
```

### Option B: GitHub Actions (Automated)

Simply push to `main` branch:

```bash
git push origin main
```

GitHub Actions will:
1. Run tests and linting
2. Validate Terraform
3. Plan infrastructure changes
4. Apply infrastructure
5. Deploy Lambda function

## Step 5: Verify Deployment

### Check Lambda Function

```bash
# List Lambda functions
aws lambda list-functions --query 'Functions[?contains(FunctionName, `news-aggregator`)]'

# View Lambda logs
aws logs tail /aws/lambda/news-aggregator --follow

# Test Lambda invocation
aws lambda invoke \
  --function-name news-aggregator \
  --payload '{}' \
  response.json

cat response.json
```

### Check DynamoDB Table

```bash
# List tables
aws dynamodb list-tables

# Describe articles table
aws dynamodb describe-table --table-name news-articles

# Scan for articles
aws dynamodb scan --table-name news-articles --max-items 5
```

### Check EventBridge Schedule

```bash
# List schedules
aws scheduler list-schedules

# View schedule details
aws scheduler get-schedule --name news-aggregator-schedule
```

### Check CloudWatch Logs

```bash
# View recent logs
aws logs tail /aws/lambda/news-aggregator --follow

# View errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/news-aggregator \
  --filter-pattern "ERROR"
```

## Troubleshooting

### Lambda Function Not Invoked

1. Check EventBridge schedule is enabled
2. Verify Lambda has EventBridge invoke permission
3. Check CloudWatch Logs for errors

### No Articles in DynamoDB

1. Check feed URLs in `config/feeds.yaml` are valid
2. Verify RSS feeds are responding
3. Check Lambda logs for ingestion errors

### Summarization Not Working

1. Verify OpenAI API key is correct
2. Check API key has sufficient quota
3. Monitor OpenAI error logs

### Slack Messages Not Sending

1. Verify webhook URLs are correct
2. Test webhook URL manually:
```bash
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test"}' \
  YOUR_WEBHOOK_URL
```
3. Check Lambda logs for Slack errors

## Scaling & Optimization

### DynamoDB

- Adjust read/write capacity based on load
- Enable auto-scaling (already configured)
- Monitor capacity utilization in CloudWatch

### Lambda

- Increase memory if timeouts occur (currently 512MB)
- Increase timeout if processing large feeds (currently 5 min)
- Reduce if costs are too high

### EventBridge

- Adjust cron schedule for frequency
- Current: `cron(0 */6 * * ? *)` (every 6 hours)
- Options: hourly `cron(0 * * * ? *)`, daily `cron(0 12 * * ? *)`

## Monitoring & Alerts

### Create SNS Topic for Alarms

```bash
aws sns create-topic --name news-aggregator-alerts

# Get ARN for CloudFormation
aws sns get-topic-attributes \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:news-aggregator-alerts \
  --attribute-names TopicArn
```

### Update Terraform

Add to `terraform.prod.tfvars`:
```hcl
alarm_actions = ["arn:aws:sns:us-east-1:ACCOUNT:news-aggregator-alerts"]
```

## Cleanup

### Destroy Infrastructure

```bash
cd infra/terraform
terraform destroy -var-file=terraform.prod.tfvars
```

### Remove AWS Resources

```bash
# Delete S3 state bucket
aws s3 rb s3://news-aggregator-terraform-state --force

# Delete OIDC provider
aws iam delete-open-id-connect-provider \
  --open-id-connect-provider-arn arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com

# Delete IAM role
aws iam delete-role-policy \
  --role-name news-aggregator-github-actions \
  --policy-name news-aggregator-github-actions-policy
aws iam delete-role --role-name news-aggregator-github-actions
```

## Cost Estimation

### Typical Monthly Costs (Dev)

- **Lambda**: ~$0.20 (1M requests/month at 1GB memory)
- **DynamoDB**: ~$1.25 (on-demand)
- **OpenAI API**: ~$2-5 (depending on usage)
- **CloudWatch**: ~$0.50 (logs)

**Total: ~$4-7/month**

### Typical Monthly Costs (Prod)

- **Lambda**: ~$0.50 (2M requests/month)
- **DynamoDB**: ~$2-3 (provisioned + auto-scaling)
- **OpenAI API**: ~$10-20 (higher usage)
- **CloudWatch**: ~$1 (more logs)
- **Terraform State**: ~$0.50 (S3)

**Total: ~$14-27/month**

## Support

For issues or questions:
1. Check CloudWatch Logs
2. Review GitHub Actions workflow runs
3. Verify all secrets are set correctly
4. Check AWS resource quotas
