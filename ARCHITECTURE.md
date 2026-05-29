# Architecture

## System Overview

The news aggregator is a serverless, event-driven system that runs on a schedule, collects articles from RSS feeds, filters and summarises them using OpenAI, and posts digests to Slack.

```
EventBridge Scheduler
        │
        ▼
  AWS Lambda (Python)
        │
        ├── feedparser (RSS ingestion, concurrent)
        │
        ├── OpenAI API (LLM classification — one batch call)
        │
        ├── trafilatura (full article fetch, concurrent)
        │
        ├── DynamoDB (deduplication + persistence)
        │
        ├── OpenAI API (summarisation)
        │
        └── Slack Workflow Webhooks (one plain text digest per topic channel)
```

## Pipeline

Requests are ordered to minimise cost and latency — cheap operations first, expensive ones only for articles that survive earlier filters.

### Step 1: Ingest

All feeds are fetched concurrently (`MAX_CONCURRENT_FEEDS`, default 10) using `feedparser`. Each article's title and RSS summary are stored as-is. No full article text is fetched at this stage.

Articles older than the cutoff are discarded here before anything else runs. The cutoff is the most recent of:
- `now - MAX_ARTICLE_AGE_HOURS` (default 60h — hard cap, covers weekend gaps)
- the timestamp of the last successful run (stored in `config/.last_run` locally or `/tmp/.last_run` in Lambda, with DynamoDB as the authoritative source when persistence is enabled)

This means hourly runs only process the last hour's articles. If the pipeline hasn't run for 3 days it still caps at 24 hours.

### Step 2: LLM Classification, Filter and Story Clustering

All article titles and summaries are sent to OpenAI in a **single batch API call**. The LLM returns topic assignments (`tech`, `ai`, `cyber_security`, `education`) and discards articles that don't match any topic (general news, sport, weather etc.).

A second LLM call then **clusters same-story articles** — multiple outlets covering the same event are merged into one entry. The richest article (most content) becomes the primary; other URLs are stored as `related_urls`. Slack shows all source URLs under a single summary, labelled "multiple sources".

If the LLM call fails, `KeywordClassifier` is used as a fallback. Both classifiers implement the same `classify_and_filter` interface.

### Step 3: Content Enrichment

Full article text is fetched concurrently for matched articles only using `trafilatura`. If the RSS feed already provides sufficient content (≥200 chars), the fetch is skipped.

### Step 4: Deduplication

Three-layer deduplication against articles already in DynamoDB:
1. **Exact URL** — fastest, O(1) hash lookup
2. **Content hash** — catches identical content reposted under different URLs
3. **Fuzzy title** — `rapidfuzz.fuzz.ratio` ≥ 85 for same-source articles, catches near-identical headlines

### Step 5: Persistence

Unique articles are written to DynamoDB. Optional — controlled by `ENABLE_PERSISTENCE`.

### Step 6: Summarisation

New articles are summarised concurrently (`MAX_CONCURRENT_SUMMARIZATIONS`, default 5) via OpenAI `gpt-4o-mini`. Each summary is 2–3 sentences and cached in DynamoDB.

### Step 7: Slack Digests

One plain text message per topic channel via Slack Workflow Builder webhooks. Each message is sent as a `payload` string variable containing title, clickable URL, summary, and source/date for each article. Controlled by `ENABLE_SLACK` (`true` / `false` / `log`).

## DynamoDB Schema

**Table**: `news-articles`

**Primary key**:
- PK: `ARTICLE#{uuid}`
- SK: `METADATA`

**Attributes**:
```
article_id       UUID
title            Article headline
source           Source domain (e.g. techcrunch.com)
url              Original article URL
published_at     ISO timestamp from feed
content          Article text (RSS summary or fetched full text)
content_hash     SHA256 of content (dedup)
topics           List of matched topic strings
first_seen_at    When first ingested
last_seen_at     Last time seen in a feed
last_summary     Cached OpenAI summary
update_count     Number of times the article has been updated
fetched_at       When this version was fetched
```

**Global Secondary Indexes**:
- `url_index`: PK `URL#{url}` — fast URL lookups for deduplication
- `source_date_index`: PK `SOURCE#{source}`, SK `DATE#{timestamp}` — query by source and date range

## AWS Infrastructure

| Component | Purpose | Config |
|---|---|---|
| Lambda | Runs the pipeline | Python 3.12, 512MB, 5-min timeout |
| EventBridge Scheduler | Triggers Lambda on schedule | Every hour (prod) |
| DynamoDB | Article storage | PAY_PER_REQUEST, PITR in prod |
| S3 | Lambda packages + Terraform state | Versioned, encrypted |
| CloudWatch | Logs and metrics | JSON-structured logs |

Resource names follow the pattern `news-aggregator-{environment}` so prod, dev, and ephemeral test environments coexist without collision.

## CI/CD Pipeline

```
Every push
    ├── lint + unit tests + Terraform validate   (always)
    └── [DEPLOY_ENABLED=true]
            ├── build Lambda → upload to S3
            ├── deploy ephemeral test env (test-{run-id})
            │       ├── invoke Lambda
            │       ├── assert DynamoDB has articles
            │       └── destroy (always, even on failure)
            └── [main branch only]
                    └── deploy prod
```

Terraform state is stored in S3 with environment-specific keys (`prod/terraform.tfstate`, `test-{id}/terraform.tfstate`). The same Terraform configuration deploys any environment — the `environment` variable and `-backend-config` flags handle the differences.

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `AWS_REGION` | AWS region | `eu-west-1` |
| `AWS_ENDPOINT_URL` | Override endpoint for LocalStack | unset |
| `DYNAMODB_TABLE` | DynamoDB table name | `news-articles` |
| `OPENAI_API_KEY` | OpenAI API key | required |
| `OPENAI_MODEL` | Model for classification + summarisation | `gpt-4o-mini` |
| `ENABLE_SLACK` | `true` / `false` / `log` | `true` |
| `ENABLE_SUMMARIZATION` | Enable OpenAI summarisation | `true` |
| `ENABLE_PERSISTENCE` | Enable DynamoDB writes | `true` |
| `ENABLE_LLM_CLASSIFICATION` | Use LLM to classify (falls back to keywords) | `true` |
| `FEED_CONFIG_PATH` | Path to feeds.yaml | resolved relative to lambda_handler.py |
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FILE` | Write logs to file (local only) | `logs/run.log` |
| `MAX_ARTICLES_PER_FEED` | Articles fetched per feed per run | `50` |
| `MAX_CONCURRENT_FEEDS` | Parallel feed/article fetches | `10` |
| `FEED_TIMEOUT` | Seconds to wait for each feed HTTP request | `20` |
| `MAX_CONCURRENT_SUMMARIZATIONS` | Parallel OpenAI summarisation calls | `5` |
| `MAX_ARTICLE_AGE_HOURS` | Discard articles older than this (0 = disabled) | `60` |
| `LAST_RUN_FILE` | Path to last run timestamp file | `config/.last_run` (local), `/tmp/.last_run` (Lambda) |

## RSS Feed Configuration

`config/feeds.yaml` — list of feed URLs. Topics are determined automatically by the classifier.

```yaml
feeds:
  - url: "https://feeds.bbci.co.uk/news/rss.xml"
  - url: "https://techcrunch.com/feed/"
```

## Resilience

- Feed unavailable → logged, skipped, pipeline continues
- LLM classification fails → falls back to keyword classifier
- Article fetch fails → uses RSS summary as-is
- OpenAI summarisation fails → article posted without summary
- Slack webhook fails → logged, other topics still posted
- DynamoDB error → logged, pipeline continues without persistence

## Performance

With 48 feeds and `MAX_ARTICLES_PER_FEED=50`:

| Stage | Time | Notes |
|---|---|---|
| Feed ingestion | 10–20s | Concurrent — wall time ≈ slowest single feed |
| LLM classification | 5–15s | Single batch API call for all articles |
| Content enrichment | 15–30s | Concurrent — only for matched articles |
| Deduplication | <1s | In-memory with DynamoDB lookup |
| Summarisation | 30–90s | Per-article OpenAI call |
| Slack | <5s | One HTTP call per matched topic |
| **Total** | **~1–3 min** | |

The classify-first approach means content enrichment only runs for matched articles. On a typical run ~20–30% of articles match a topic, so roughly 70% of potential article fetches are avoided.
