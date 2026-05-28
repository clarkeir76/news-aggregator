# Quick Start Guide

## 5-Minute Local Setup

### Prerequisites
- Python 3.12
- `pip` and `venv`

### Installation

```bash
# 1. Clone or navigate to project
cd news-aggregator

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # or: venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and edit configuration
cp .env.example .env
# Edit .env: disable Slack and summarization for local testing
```

### Run Locally

```bash
# Test ingestion and classification only
python -c "
from app.src.ingestion import FeedConfig, RSSIngester
from app.src.classification import KeywordClassifier

configs = FeedConfig.load_from_yaml('config/feeds.yaml')
ingester = RSSIngester(max_articles_per_feed=5)
articles, stats = ingester.ingest_feeds(configs)
print(f'Ingested {len(articles)} articles')

classifier = KeywordClassifier()
articles = classifier.classify_articles(articles)
for article in articles[:3]:
    print(f'{article.title} -> {article.topics}')
"
```

## 10-Minute Development Setup

### Docker

```bash
# Build and run with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f app
```

### With LocalStack (Local AWS Emulation)

```bash
# Start LocalStack with news aggregator
docker-compose up -d localstack

# Configure AWS CLI to use LocalStack
export AWS_ENDPOINT_URL=http://localhost:4566
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test

# Create DynamoDB table
aws dynamodb create-table \
  --table-name news-articles \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST

# Test with app
python app/lambda_handler.py
```

## Run Tests

```bash
# Install test dependencies
make dev-install

# Run tests
make test

# Run with coverage
make test-cov

# Run specific test
pytest tests/test_models.py -v
```

## Code Quality Checks

```bash
# Format code (automatic)
make format

# Check formatting
black --check app/ tests/

# Lint
make lint

# Type checking
mypy app/src/ --ignore-missing-imports
```

## Deploy to AWS

### Step 1: Prerequisites

```bash
# Set AWS credentials
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1

# Or configure with AWS CLI
aws configure
```

### Step 2: Create Terraform State Bucket

```bash
aws s3 mb s3://news-aggregator-terraform-state
aws s3api put-bucket-versioning \
  --bucket news-aggregator-terraform-state \
  --versioning-configuration Status=Enabled
```

### Step 3: Deploy Infrastructure

```bash
cd infra/terraform

# Initialize
terraform init

# Plan changes (development)
terraform plan -var-file=terraform.dev.tfvars

# Apply changes
terraform apply -var-file=terraform.dev.tfvars
```

### Step 4: Deploy Lambda Function

```bash
# From project root
make lambda-build

# Deploy using AWS CLI
aws lambda update-function-code \
  --function-name news-aggregator \
  --zip-file fileb://lambda_function.zip
```

## Common Commands

```bash
# Development
make dev-install      # Install all dependencies
make dev-run          # Run Lambda handler locally
make test             # Run tests
make lint             # Check code quality
make format           # Format code

# Lambda
make lambda-build     # Build Lambda package

# Terraform
make tf-init          # Initialize Terraform
make tf-plan          # Plan infrastructure
make tf-apply         # Apply infrastructure
make tf-destroy       # Destroy infrastructure

# Docker
make docker-build     # Build Docker image
make docker-run       # Run Docker container

# Cleanup
make clean            # Remove build artifacts
```

## Troubleshooting

### Feed Parsing Issues

```bash
# Test feed URL
python -c "
import feedparser
feed = feedparser.parse('https://example.com/rss')
print(f'Title: {feed.feed.title}')
print(f'Entries: {len(feed.entries)}')
"
```

### DynamoDB Errors

```bash
# Check if table exists
aws dynamodb list-tables

# Describe table
aws dynamodb describe-table --table-name news-articles

# Scan table
aws dynamodb scan --table-name news-articles --max-items 5
```

### Lambda Logs

```bash
# View recent logs
aws logs tail /aws/lambda/news-aggregator --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/news-aggregator \
  --filter-pattern "ERROR"
```

### OpenAI API Issues

```bash
# Check API key
python -c "
import openai
openai.api_key = 'sk-...'
print(openai.api_key[:10])
"

# Test API
python -c "
import openai
openai.api_key = 'sk-...'
response = openai.ChatCompletion.create(
    model='gpt-4o-mini',
    messages=[{'role': 'user', 'content': 'Hello'}]
)
print(response['choices'][0]['message']['content'])
"
```

## Configuration Reference

### `config/feeds.yaml`
List of RSS feeds to monitor:
```yaml
feeds:
  - url: "https://news.ycombinator.com/rss"
    topics: ["tech"]
```

### `.env`
Environment variables:
```
OPENAI_API_KEY=sk-...
AWS_REGION=us-east-1
DYNAMODB_TABLE=news-articles
LOG_LEVEL=DEBUG
```

### `infra/terraform/terraform.dev.tfvars`
Development infrastructure variables

### `infra/terraform/terraform.prod.tfvars`
Production infrastructure variables

## Next Steps

1. **Add more RSS feeds**: Edit `config/feeds.yaml`
2. **Customize topics**: Modify `app/src/classification.py`
3. **Deploy to AWS**: Follow "Deploy to AWS" section
4. **Setup GitHub OIDC**: Run `.github/scripts/setup-oidc.py`
5. **Create GitHub secrets**: Add deployment credentials
6. **Push to main**: Trigger automated deployment

## Support

- Check [README.md](README.md) for overview
- Check [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design
- Check [API.md](API.md) for module documentation
- Check [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment
