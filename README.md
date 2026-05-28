# News Aggregator

A production-style Python news aggregation and summarization system that pulls stories from multiple RSS feeds, categorizes them, deduplicates them, summarizes them using OpenAI, and posts to Slack.

## Overview

This system demonstrates:
- **AI Integration**: OpenAI API for intelligent summarization
- **Cloud Engineering**: AWS Lambda, DynamoDB, EventBridge, CloudWatch
- **Infrastructure as Code**: Terraform with modular design
- **CI/CD**: GitHub Actions with GitHub OIDC authentication
- **Production Practices**: Logging, error handling, monitoring

## Architecture

```
RSS Feeds
   ↓
[Ingestion] - Fetch articles from multiple RSS feeds
   ↓
[Classification] - Categorize into topics using keywords
   ↓
[Deduplication] - Remove duplicates (exact URL, content hash, fuzzy title)
   ↓
[Persistence] - Store in DynamoDB with update detection
   ↓
[Summarization] - Generate concise summaries via OpenAI
   ↓
[Slack Notification] - Post to topic-specific channels
```

### AWS Architecture

```
EventBridge Scheduler → Lambda Function → DynamoDB
                            ↓
                       OpenAI API
                            ↓
                       Slack Webhooks
```

## Setup

### Prerequisites

- Python 3.12+
- AWS Account with appropriate permissions
- Terraform >= 1.0
- OpenAI API key
- Slack workspace with admin access
- GitHub account for CI/CD

### Local Development

1. **Clone and setup**:
   ```bash
   git clone <repository>
   cd news-aggregator
   make dev-install
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Configure feeds**:
   ```bash
   # Edit config/feeds.yaml to add/remove RSS feeds
   ```

4. **Run locally**:
   ```bash
   make dev-run
   ```

5. **Run tests**:
   ```bash
   make test
   ```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | us-east-1 |
| `DYNAMODB_TABLE` | DynamoDB table name | news-articles |
| `OPENAI_API_KEY` | OpenAI API key | Required |
| `OPENAI_MODEL` | OpenAI model | gpt-4o-mini |
| `ENABLE_SLACK` | Enable Slack notifications | true |
| `ENABLE_SUMMARIZATION` | Enable OpenAI summarization | true |
| `LOG_LEVEL` | Logging level | INFO |
| `MAX_ARTICLES_PER_FEED` | Articles per RSS feed | 50 |

### Slack Webhooks

Set individual webhook URLs for each topic:
- `SLACK_WEBHOOK_TECH`
- `SLACK_WEBHOOK_AI`
- `SLACK_WEBHOOK_EDUCATION`
- `SLACK_WEBHOOK_CYBER_SECURITY`

[Create webhooks in Slack](https://api.slack.com/messaging/webhooks)

### RSS Feeds

Edit `config/feeds.yaml`:

```yaml
feeds:
  - url: "https://news.ycombinator.com/rss"
    topics: ["tech"]
  - url: "https://arxiv.org/list/cs.AI/rss"
    topics: ["ai"]
```

## Project Structure

```
news-aggregator/
├── app/
│   ├── src/                    # Python modules
│   │   ├── __init__.py
│   │   ├── config.py           # Configuration management
│   │   ├── logging_setup.py    # Structured logging
│   │   ├── models.py           # Data models
│   │   ├── ingestion.py        # RSS feed ingestion
│   │   ├── classification.py   # Topic classification
│   │   ├── deduplication.py    # Deduplication logic
│   │   ├── persistence.py      # DynamoDB storage
│   │   ├── summarization.py    # OpenAI summarization
│   │   ├── slack_notifier.py   # Slack integration
│   │   └── orchestrator.py     # Main pipeline
│   └── lambda_handler.py       # AWS Lambda entry point
├── infra/
│   └── terraform/              # Infrastructure as Code
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       └── modules/
│           ├── lambda/
│           ├── dynamodb/
│           ├── eventbridge/
│           └── secrets/
├── tests/                      # Unit tests
├── config/
│   └── feeds.yaml             # RSS feed configuration
├── .github/
│   └── workflows/             # GitHub Actions CI/CD
├── requirements.txt           # Python dependencies
├── .env.example              # Environment variables template
├── Makefile                  # Development commands
└── README.md                 # This file
```

## Core Modules

### Ingestion (`ingestion.py`)

- **Fetches** articles from RSS feeds using `feedparser`
- **Normalizes** to common Article schema
- **Extracts** title, URL, content, publish date, source
- **Handles** malformed feeds gracefully

```python
from app.src.ingestion import RSSIngester, FeedConfig

configs = FeedConfig.load_from_yaml("config/feeds.yaml")
ingester = RSSIngester(max_articles_per_feed=50)
articles, stats = ingester.ingest_feeds(configs)
```

### Classification (`classification.py`)

- **Keyword-based** topic matching (easy to swap with LLM)
- **Multiple topics** per article supported
- **Extensible** - add new topics and keywords easily

```python
from app.src.classification import KeywordClassifier

classifier = KeywordClassifier()
articles = classifier.classify_articles(articles)
# articles[0].topics = ["tech", "ai"]
```

### Deduplication (`deduplication.py`)

Prevents posting duplicate stories using:

1. **Exact URL match** - Same article from same source
2. **Content hash** - Same content from different sources
3. **Fuzzy title matching** - Similar titles from same source (85%+ similarity)

```python
from app.src.deduplication import Deduplicator

dedup = Deduplicator(title_similarity_threshold=0.85)
unique, stats = dedup.deduplicate(articles, existing_articles)
# Returns unique articles and deduplication stats
```

### Persistence (`persistence.py`)

DynamoDB storage with:
- **Article metadata** (ID, source, URL, published date)
- **Update tracking** (first_seen_at, last_seen_at, update_count)
- **Summaries** (last_summary cached)
- **GSI queries** for efficient lookups

```python
from app.src.persistence import DynamoDBStore

store = DynamoDBStore("news-articles", region_name="us-east-1")
article_id = store.save_article(article)
store.update_article(article_id, {"last_summary": summary})
```

### Summarization (`summarization.py`)

OpenAI integration for concise summaries:
- Uses `gpt-4o-mini` (fast, affordable)
- Generates 2-3 sentence summaries
- Highlights what's new for updated articles
- Handles API errors gracefully

```python
from app.src.summarization import Summarizer

summarizer = Summarizer(api_key="sk-...", model="gpt-4o-mini")
summary = summarizer.summarize(article.content, article.title)
```

### Slack Integration (`slack_notifier.py`)

Topic-specific webhook notifications:
- Formatted messages with emoji, fields, links
- Separate summaries for new vs. updated articles
- Batch notification support

```python
from app.src.slack_notifier import SlackNotifier

notifier = SlackNotifier({
    "tech": "https://hooks.slack.com/...",
    "ai": "https://hooks.slack.com/..."
})
notifier.notify_batch(articles, summaries)
```

## Deployment

### AWS Setup

1. **Create S3 bucket for Terraform state**:
   ```bash
   aws s3 mb s3://news-aggregator-terraform-state
   ```

2. **Set up GitHub OIDC** for AWS authentication:
   ```bash
   # See infra/terraform/github-oidc-setup.sh
   ```

3. **Initialize Terraform**:
   ```bash
   make tf-init
   ```

4. **Plan infrastructure**:
   ```bash
   make tf-plan
   ```

5. **Deploy infrastructure**:
   ```bash
   make tf-apply
   ```

### GitHub Actions CI/CD

Pipeline automatically:
- ✅ Runs linting and tests on PR
- ✅ Packages Lambda function
- ✅ Validates Terraform
- ✅ Deploys to AWS (main branch)

Requires:
- AWS account ID as GitHub secret
- GitHub OIDC role in AWS

## Development

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/test_models.py -v
```

### Code Quality

```bash
# Format code
make format

# Lint and type check
make lint
```

### Local Testing

```bash
# Run Lambda handler locally
make dev-run

# With Docker
make docker-build
make docker-run
```

## Design Decisions & Trade-offs

### Why these technologies?

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Ingestion** | feedparser | Simple, reliable RSS parsing |
| **Classification** | Keywords → LLM-ready | Easy to migrate to LLM classification |
| **Deduplication** | Hybrid (exact+fuzzy) | Catches duplicates without over-filtering |
| **Persistence** | DynamoDB | Serverless, pay-per-request, GSI queries |
| **Summarization** | gpt-4o-mini | Fast, affordable, good quality |
| **Deployment** | Lambda | Serverless, event-driven, pay-per-execution |
| **Scheduling** | EventBridge | Native AWS, cron expressions |
| **CI/CD** | GitHub Actions + OIDC | No long-lived credentials, native GitHub integration |

### Trade-offs

1. **Keyword classification** vs **LLM classification**
   - ✅ Faster, cheaper, deterministic
   - ❌ Less accurate for nuance
   - 🔄 Easy to migrate to LLM later

2. **Exact URL deduplication** vs **Fuzzy**
   - ✅ Different sources get notified
   - ❌ May miss some duplicates
   - 🔄 Combined approach balances both

3. **gpt-4o-mini** vs **gpt-4**
   - ✅ 10x cheaper, very fast
   - ❌ Slightly lower quality
   - 🔄 Excellent for news summaries

4. **DynamoDB** vs **PostgreSQL**
   - ✅ Serverless, scales easily
   - ❌ No complex joins
   - 🔄 Right for this use case

## Future Enhancements

### Short-term
- [ ] LLM-based topic classification with fine-tuning
- [ ] Sentiment analysis for articles
- [ ] Reader/engagement metrics from sources
- [ ] Email digest delivery
- [ ] Web UI dashboard

### Medium-term
- [ ] Support for other content (APIs, webhooks)
- [ ] Story cluster detection (same story from many sources)
- [ ] Trends analysis ("what's trending in tech")
- [ ] Custom filtering per user
- [ ] Browser extension for bookmarking

### Long-term
- [ ] Multi-user system with preferences
- [ ] Machine learning model for content quality
- [ ] Video/image content support
- [ ] Real-time streaming (instead of scheduled)
- [ ] Integration with other platforms (Twitter, Discord, etc.)

## Monitoring & Logging

### CloudWatch Logs

Lambda execution logs are automatically sent to CloudWatch:

```bash
# View logs
aws logs tail /aws/lambda/news-aggregator --follow
```

### Structured Logging

All logs are JSON-formatted for easy parsing:

```json
{
  "timestamp": "2024-01-15T10:30:45.123456",
  "level": "INFO",
  "logger": "app.src.orchestrator",
  "message": "Ingested 45 total articles"
}
```

### CloudWatch Metrics

Custom metrics published:
- Articles processed
- Summaries generated
- Slack notifications sent
- Errors encountered

## Troubleshooting

### OpenAI API errors

```
OpenAI API error: RateLimitError
```
- Wait a moment and retry
- Check your rate limits: https://platform.openai.com/account/rate-limits
- Consider switching to a different model

### DynamoDB errors

```
ResourceNotFoundException: Table not found
```
- Ensure Terraform has been deployed
- Check table name in environment variables
- Verify AWS credentials and region

### Slack webhook errors

```
Slack webhook returned 404
```
- Regenerate webhook URL from Slack
- Verify the webhook URL is correct
- Check that the channel still exists

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `make test`
5. Submit a pull request

## Support

For issues or questions:
1. Check existing issues on GitHub
2. Create a new issue with details
3. Include logs and error messages
