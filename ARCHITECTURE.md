# Architecture Documentation

## System Overview

The News Aggregator is a serverless, event-driven system that continuously collects, processes, and distributes news articles across multiple platforms.

```
┌─────────────────────────────────────────────────────────────┐
│                     Event Triggers                           │
│  (EventBridge Scheduler - Every 6 hours)                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  AWS Lambda (Python)                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                 Orchestrator                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │  │
│  │  │  Ingestion   │  │ Classification│  │  Dedupe    │ │  │
│  │  │  (RSS Feeds) │  │ (Keywords)    │  │  (Fuzzy+  │ │  │
│  │  │              │  │                │  │   Exact)   │ │  │
│  │  └──────────────┘  └──────────────┘  └────────────┘ │  │
│  │         │                │                 │         │  │
│  │         ▼                ▼                 ▼         │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │           DynamoDB Persistence              │   │  │
│  │  │   (Articles with update tracking)           │   │  │
│  │  └──────────────────────────────────────────────┘   │  │
│  │         │                                           │  │
│  │         ▼                                           │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │     OpenAI Summarization                     │   │  │
│  │  │   (gpt-4o-mini, ~$0.0001 per article)       │   │  │
│  │  └──────────────────────────────────────────────┘   │  │
│  │         │                                           │  │
│  │         ▼                                           │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │     Slack Notification                       │   │  │
│  │  │   (Topic-specific channels)                  │   │  │
│  │  └──────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Logs → CloudWatch Logs                                   │
│  Metrics → CloudWatch Metrics                             │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Ingestion Phase
- **Input**: RSS feed URLs from `config/feeds.yaml`
- **Process**: Fetch latest articles from each feed using `feedparser`
- **Output**: List of `Article` objects with normalized schema
- **Error Handling**: Graceful degradation if feeds are unavailable

### 2. Classification Phase
- **Input**: Articles without topics
- **Process**: Keyword matching against category dictionaries
- **Output**: Articles with topic tags (can be multiple)
- **Future**: Replaceable with LLM-based classifier

### 3. Deduplication Phase
- **Input**: New articles + existing articles from DynamoDB
- **Process**: Multi-layer deduplication:
  1. **Exact URL matching** - Same article from same source
  2. **Content hash** - Same content reposted elsewhere
  3. **Fuzzy title** - Similar titles from same source (>85% similarity)
- **Output**: Unique articles only
- **Goal**: Prevent duplicate notifications while catching legitimate updates

### 4. Persistence Phase
- **Input**: Deduplicated articles
- **Process**: Store in DynamoDB with metadata
- **Update Detection**: If article exists, increment `update_count` and update `last_seen_at`
- **Output**: Article IDs for tracking
- **Storage**: ~50KB per article (title, URL, summary, metadata)

### 5. Summarization Phase
- **Input**: Article content
- **Process**: Call OpenAI API with article title and content
- **Prompt**: Request 2-3 sentence summary with key information
- **Output**: Summary text cached in DynamoDB
- **Cost**: ~$0.0001-0.0005 per summary

### 6. Notification Phase
- **Input**: Articles and summaries
- **Process**: Route to appropriate Slack channels by topic
- **Format**: Nicely formatted Rich Messages with emoji, links, fields
- **Feature**: Different formatting for updates vs. new articles
- **Error Handling**: Graceful failure if webhooks unavailable

## Database Schema

### DynamoDB Table: `news-articles`

**Partition Key (PK)**: `ARTICLE#{article_id}` (UUID)
**Sort Key (SK)**: `METADATA#{timestamp}`

**Attributes**:
```
pk                    → Partition key
sk                    → Sort key
article_id           → UUID
title                → Article title
source               → Source domain
url                  → Article URL (unique per source)
published_at         → Original publish time
content              → Article text/summary
topics               → List of topic tags
content_hash         → SHA256 of content
canonical_url        → Normalized URL
first_seen_at        → When first discovered
last_seen_at         → Last time seen
last_summary         → Cached OpenAI summary
update_count         → Number of updates seen
is_new               → Boolean
fetched_at           → When fetched by aggregator
```

**Global Secondary Indexes**:

1. **url_index**: Quick lookup by URL
   - PK: `url_gsi_pk` (URL#{url})
   - Projects all attributes

2. **source_date_index**: Query articles by source/date
   - PK: `source_date_gsi_pk` (SOURCE#{source})
   - SK: `source_date_gsi_sk` (DATE#{timestamp})
   - Projects all attributes

**Capacity**:
- Dev: 5 RCU / 5 WCU
- Prod: 20 RCU / 20 WCU with auto-scaling up to 100

## AWS Infrastructure

### Compute
- **Lambda**: Serverless function execution
  - Runtime: Python 3.12
  - Memory: 512 MB (prod) / 256 MB (dev)
  - Timeout: 5 minutes
  - Triggers: EventBridge Schedule

### Scheduling
- **EventBridge Scheduler**: Cron-based invocation
  - Prod: Every 6 hours `cron(0 */6 * * ? *)`
  - Dev: Daily at noon `cron(0 12 * * ? *)`
  - Dead Letter Queue for failed invocations

### Storage
- **DynamoDB**: Serverless NoSQL database
  - On-demand or provisioned capacity
  - Point-in-time recovery (prod only)
  - Encryption at rest with KMS
  - Stream support for future features

### Secrets
- **Secrets Manager**: Secure credential storage
  - OpenAI API key
  - Slack webhook URLs (one per topic)
  - Automatic rotation support

### Monitoring
- **CloudWatch Logs**: Application logs (JSON-formatted)
- **CloudWatch Metrics**: Lambda duration, errors, DynamoDB throughput
- **CloudWatch Alarms**: Error thresholds, performance degradation

### Security
- **IAM Roles**: Least-privilege access
  - Lambda role: DynamoDB, Secrets, CloudWatch
  - EventBridge role: Lambda invocation
- **KMS**: Encryption for DynamoDB
- **VPC** (optional): Deploy Lambda in private subnets

## Configuration Management

### Environment Variables
```
AWS_REGION              # AWS region (us-east-1)
DYNAMODB_TABLE         # Table name (news-articles)
OPENAI_API_KEY         # API key (from Secrets Manager)
OPENAI_MODEL           # Model (gpt-4o-mini)
ENABLE_SLACK           # Feature flag (true/false)
ENABLE_SUMMARIZATION   # Feature flag (true/false)
LOG_LEVEL              # DEBUG/INFO/WARNING/ERROR
MAX_ARTICLES_PER_FEED  # Limit per feed (50)
```

### RSS Feed Configuration
```yaml
feeds:
  - url: "https://example.com/rss"
    topics: ["tech", "ai"]  # Can have multiple
```

### Slack Webhook Configuration
- One webhook per topic
- Separate channels for different news types
- Example: `#news-ai`, `#news-tech`

## Scalability

### Horizontal Scaling
- **Lambda**: Auto-scales to handle concurrent requests (100+)
- **DynamoDB**: On-demand billing scales automatically
- **Secrets Manager**: No scaling needed

### Vertical Scaling
- Increase Lambda memory to improve speed
- Increase DynamoDB capacity for higher throughput
- Add more RSS feeds without code changes

### Performance Characteristics

| Operation | Time | Cost |
|-----------|------|------|
| Ingest 50 feeds (100 articles) | 30-45s | ~$0.0005 |
| Classify articles | 5-10s | ~$0.0000 |
| Deduplicate | 3-5s | ~$0.0010 |
| DynamoDB writes (100) | 2-3s | ~$0.0015 |
| OpenAI summaries (100) | 60-90s | ~$0.05 |
| Slack notifications (100) | 5-10s | ~$0.0000 |
| **Total per run** | **2-3 min** | **~$0.055** |

## Resilience & Error Handling

### Graceful Degradation
- Feed unavailable → Skip, continue with others
- OpenAI API timeout → Still post article without summary
- Slack webhook down → Log error, don't crash
- DynamoDB throttle → Automatic retry with exponential backoff

### Dead Letter Queue
- Failed Lambda invocations → SQS DLQ
- Retain for 14 days for manual recovery
- CloudWatch alarm when messages arrive

### Monitoring & Alerts
- Lambda errors > 5 in 5 minutes → Alert
- Lambda duration > 50s average → Alert
- DynamoDB throttled requests → Alert

## Cost Optimization

### Cost Drivers (Monthly)
1. Lambda execution (~$0.20/M requests)
2. DynamoDB on-demand (~$1-2)
3. OpenAI API (~$0.05/100 articles)
4. CloudWatch Logs (~$0.50/GB stored)

### Optimization Opportunities
- Use batch inference for summaries
- Adjust EventBridge frequency
- Archive old articles to S3 Glacier
- Use DynamoDB provisioned capacity for stable workloads

## Deployment Strategy

### Development
- Local testing with LocalStack
- GitHub feature branches with PR reviews
- Automated testing on every commit

### Staging
- Separate AWS account (optional)
- Same infrastructure as prod
- Manual testing before prod deployment

### Production
- Blue-green deployment via Lambda versions
- Terraform for all infrastructure
- GitHub OIDC for CD pipeline
- Gradual rollout with monitoring

## Future Enhancements

### Short-term
- [ ] LLM-based classification
- [ ] Article clustering (same story from multiple sources)
- [ ] Sentiment analysis
- [ ] User engagement metrics

### Medium-term
- [ ] Multi-user system with preferences
- [ ] Web UI for browsing articles
- [ ] Email digests
- [ ] Browser extension

### Long-term
- [ ] Video/image content support
- [ ] Real-time streaming (instead of scheduled)
- [ ] Integration with other platforms (Twitter, Discord)
- [ ] ML model for content quality scoring
