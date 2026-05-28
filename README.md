# News Aggregator

A Python news aggregation and summarisation system that pulls articles from multiple RSS feeds, classifies them by topic, deduplicates them, summarises them using OpenAI, and posts digest messages to Slack.

## Architecture

```
RSS Feeds
   ↓
[Ingestion] — fetch feeds concurrently, store title + RSS summary only (fast)
   ↓
[Classification] — LLM batch call classifies all articles at once, discards non-matches
   ↓
[Content Enrichment] — fetch full article text concurrently (only for matched articles)
   ↓
[Deduplication] — exact URL, content hash, fuzzy title (85%+ similarity)
   ↓
[Persistence] — DynamoDB (optional)
   ↓
[Summarisation] — OpenAI gpt-4o-mini
   ↓
[Slack] — one digest message per topic channel per run
```

The pipeline is ordered to minimise expensive operations: RSS fetching is fast, so all
feeds are ingested first. The LLM then discards irrelevant articles in a single batch
API call before any full article text is fetched — avoiding slow HTTP requests for news
that would be thrown away anyway.

### AWS Architecture

```
EventBridge Scheduler → Lambda Function → DynamoDB
                            ↓
                       OpenAI API
                            ↓
                    Slack Workflow Webhooks
```

## Quick Start

### Prerequisites

- Python 3.9+
- OpenAI API key
- Slack workspace (for notifications)

### Setup

```bash
git clone <repository>
cd news-aggregator

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Run locally

```bash
python app/lambda_handler.py
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `AWS_REGION` | AWS region | `us-east-1` |
| `AWS_ENDPOINT_URL` | Override AWS endpoint — set to `http://localhost:4566` for LocalStack | unset (real AWS) |
| `DYNAMODB_TABLE` | DynamoDB table name | `news-articles` |
| `OPENAI_API_KEY` | OpenAI API key | required |
| `OPENAI_MODEL` | OpenAI model | `gpt-4o-mini` |
| `ENABLE_SLACK` | Slack mode: `true` / `false` / `log` | `true` |
| `ENABLE_SUMMARIZATION` | Enable OpenAI summarisation | `true` |
| `ENABLE_PERSISTENCE` | Enable DynamoDB storage | `true` |
| `ENABLE_LLM_CLASSIFICATION` | Use LLM to classify and filter articles (falls back to keywords if disabled or no API key) | `true` |
| `FEED_CONFIG_PATH` | Path to feeds.yaml | resolved relative to lambda_handler.py |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MAX_ARTICLES_PER_FEED` | Articles fetched per RSS feed per run | `50` |
| `MAX_SUMMARY_LENGTH` | Max summary length in tokens | `300` |
| `MAX_CONCURRENT_FEEDS` | Number of feeds/article fetches in parallel | `10` |
| `FEED_TIMEOUT` | Seconds to wait for each feed HTTP request | `20` |
| `MAX_CONCURRENT_SUMMARIZATIONS` | Number of parallel OpenAI summarisation calls | `5` |
| `MAX_ARTICLE_AGE_HOURS` | Discard articles older than this. Set to `0` to disable. | `24` |
| `LAST_RUN_FILE` | Path to file storing last successful run timestamp | `logs/.last_run` |

#### ENABLE_SLACK modes

| Value | Behaviour |
|---|---|
| `true` | Send digest messages to Slack channels |
| `log` | Print digest content to terminal — no HTTP calls made |
| `false` | Slack disabled entirely |

### Slack Webhooks

This system uses **Slack Workflow Builder** webhooks (not incoming webhooks). Each topic channel needs its own webhook URL, configured in Slack Workflow Builder as a "From a webhook" trigger with a variable named `payload`.

Set the webhook URLs in `.env`:

```
SLACK_WEBHOOK_TECH=https://hooks.slack.com/triggers/...
SLACK_WEBHOOK_AI=https://hooks.slack.com/triggers/...
SLACK_WEBHOOK_EDUCATION=https://hooks.slack.com/triggers/...
SLACK_WEBHOOK_CYBER_SECURITY=https://hooks.slack.com/triggers/...
```

Omitting a variable for a topic simply means that topic won't send notifications.

### RSS Feeds

Edit `config/feeds.yaml`. Topics are determined automatically by the classifier — no per-feed topic assignment needed:

```yaml
feeds:
  - url: "https://feeds.bbci.co.uk/news/rss.xml"
  - url: "https://techcrunch.com/feed/"
  - url: "https://krebsonsecurity.com/feed/"
```

## Testing Locally

### Mode 1 — No AWS, no Slack (fastest)

Test ingestion, classification, deduplication and summarisation only:

```
ENABLE_PERSISTENCE=false
ENABLE_SLACK=false
```

### Mode 2 — Preview Slack output without sending

See exactly what would be posted to each Slack channel:

```
ENABLE_PERSISTENCE=false
ENABLE_SLACK=log
```

Digest content is printed to the terminal per topic channel.

### Mode 3 — Full local stack with LocalStack

Requires Docker. Emulates DynamoDB locally:

```
ENABLE_PERSISTENCE=true
AWS_ENDPOINT_URL=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```

Start LocalStack and create the table:

```bash
docker-compose up -d localstack

aws dynamodb create-table \
  --endpoint-url http://localhost:4566 \
  --table-name news-articles \
  --attribute-definitions AttributeName=pk,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=pk,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
```

### Mode 4 — Full AWS

```
ENABLE_PERSISTENCE=true
ENABLE_SLACK=true
# No AWS_ENDPOINT_URL — boto3 uses real AWS
```

Requires AWS credentials and deployed infrastructure (see Deployment).

### Tip: limit articles on first run

With 48 feeds at 50 articles each, the first run fetches a large number of articles and makes many OpenAI API calls. Set `MAX_ARTICLES_PER_FEED=5` in `.env` for an initial test.

### Concurrency

Feeds are fetched in parallel using a thread pool (`MAX_CONCURRENT_FEEDS=10` by default). Since feed fetching is almost entirely network I/O, this gives roughly a 5-8x speedup over sequential fetching. Reduce this value if you hit rate limits from specific sites.

## Running Tests

Tests run automatically as a pre-commit hook. To run manually:

```bash
# All tests
make test

# With coverage report
make test-cov

# Single module
pytest tests/test_classification.py -v
```

## Project Structure

```
news-aggregator/
├── app/
│   ├── src/
│   │   ├── config.py            # Environment variable loading
│   │   ├── models.py            # Article / StoredArticle dataclasses
│   │   ├── ingestion.py         # RSS feed fetching (title + summary only)
│   │   ├── classification.py    # LLMClassifier (primary) + KeywordClassifier (fallback)
│   │   ├── content_extractor.py # Full article text extraction via trafilatura
│   │   ├── deduplication.py     # URL, hash and fuzzy-title deduplication
│   │   ├── persistence.py       # DynamoDB read/write
│   │   ├── summarization.py     # OpenAI summarisation
│   │   ├── slack_notifier.py    # Slack Workflow Builder digest notifications
│   │   ├── orchestrator.py      # Pipeline wiring
│   │   └── logging_setup.py     # Structured JSON logging
│   └── lambda_handler.py        # AWS Lambda / local entry point
├── tests/                       # Unit tests (67 tests, all mocked)
├── config/
│   └── feeds.yaml               # RSS feed list
├── infra/
│   └── terraform/               # AWS infrastructure (Lambda, DynamoDB, EventBridge)
├── .github/workflows/           # CI/CD pipeline
├── .env.example                 # Environment variable reference
├── requirements.txt
└── Makefile                     # Common commands
```

## Deployment

### Prerequisites

- AWS account
- Terraform >= 1.0
- GitHub repo with Actions enabled

### Steps

1. **Create Terraform state bucket**:
   ```bash
   aws s3 mb s3://news-aggregator-terraform-state
   ```

2. **Set GitHub secrets**:
   - `AWS_ROLE_ARN` — IAM role for GitHub OIDC
   - `OPENAI_API_KEY`
   - `SLACK_WEBHOOK_TECH`, `SLACK_WEBHOOK_AI`, `SLACK_WEBHOOK_EDUCATION`, `SLACK_WEBHOOK_CYBER_SECURITY`
   - `SLACK_DEPLOYMENT_WEBHOOK` — optional, for deploy notifications

3. **Deploy infrastructure**:
   ```bash
   make tf-init
   make tf-plan
   make tf-apply
   ```

4. **Set Lambda environment variables** — mirror your `.env` in the Lambda console or via Terraform variables. Set `FEED_CONFIG_PATH=/opt/config/feeds.yaml`.

### CI/CD Pipeline

On every push to `main`:
- Lint and test
- Package Lambda function
- Terraform apply
- Deploy Lambda
- Notify Slack on completion

On every PR:
- Lint and test
- Terraform validate and plan (plan posted as PR comment)

## Code Quality

```bash
make format   # auto-format with black
make lint     # black check + flake8 + mypy
```

## Troubleshooting

**`ResourceNotFoundException: Table not found`**
- Check `DYNAMODB_TABLE` matches the deployed table name
- Check `AWS_REGION` is correct
- For LocalStack, verify `AWS_ENDPOINT_URL=http://localhost:4566`

**OpenAI `RateLimitError`**
- Reduce `MAX_ARTICLES_PER_FEED` to limit API calls per run

**Slack webhook returning 404**
- Regenerate the webhook URL in Slack Workflow Builder
- Ensure the workflow is published (not just saved as draft)

**Feed returning no articles**
- Check the URL still works in a browser
- Some feeds block automated requests — comment out and find an alternative

## License

MIT
