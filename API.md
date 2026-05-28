# API Documentation

## Core Module APIs

### `ingestion.py` - RSS Feed Ingestion

#### `FeedConfig.load_from_yaml(config_path: str) -> List[FeedConfig]`
Load RSS feed configuration from YAML file.

**Parameters**:
- `config_path` (str): Path to feeds.yaml file

**Returns**: List of FeedConfig objects

**Example**:
```python
from app.src.ingestion import FeedConfig

configs = FeedConfig.load_from_yaml("config/feeds.yaml")
for config in configs:
    print(config.url)
```

#### `RSSIngester.ingest_feed(feed_url: str) -> Tuple[List[Article], int]`
Ingest a single RSS feed. Stores title and RSS summary only — full article text is fetched later by the orchestrator after classification.

**Parameters**:
- `feed_url` (str): URL of RSS feed

**Returns**: Tuple of (articles, error_count)

**Raises**: Network errors are logged but not raised

**Example**:
```python
ingester = RSSIngester(max_articles_per_feed=50, max_concurrent_feeds=10)
articles, errors = ingester.ingest_feed("https://news.ycombinator.com/rss")
print(f"Got {len(articles)} articles with {errors} errors")
```

#### `RSSIngester.ingest_feeds(feed_configs: List[FeedConfig]) -> Tuple[List[Article], dict]`
Ingest multiple RSS feeds.

**Parameters**:
- `feed_configs` (List[FeedConfig]): List of feed configurations

**Returns**: Tuple of (all_articles, stats_dict)

**Stats dict**:
```python
{
    "total_feeds": 10,
    "successful_feeds": 9,
    "failed_feeds": 1,
    "total_articles": 150,
    "total_errors": 5
}
```

---

### `classification.py` - Topic Classification

Two classifiers are available, both implementing the `classify_and_filter` interface. `LLMClassifier` is used by default when an OpenAI API key is present; `KeywordClassifier` is the fallback.

#### `LLMClassifier.classify_and_filter(articles: List[Article]) -> List[Article]`
Classify and filter articles using a single batched LLM call. Discards articles that don't match any topic. Falls back to `KeywordClassifier` if the API call fails.

**Parameters**:
- `articles` (List[Article]): Articles with title and RSS summary populated

**Returns**: Filtered list with `topics` set on each article

**Example**:
```python
classifier = LLMClassifier(api_key="sk-...")
matched = classifier.classify_and_filter(articles)
# matched contains only relevant articles, each with topics assigned
```

#### `KeywordClassifier.classify_and_filter(articles: List[Article]) -> List[Article]`
Classify articles using keyword matching. Keeps all articles (no articles are discarded — keyword matching has no confidence in rejection).

**Parameters**:
- `articles` (List[Article]): Articles to classify

**Returns**: All articles with `topics` set; defaults to `["tech"]` if no keywords match

**Example**:
```python
classifier = KeywordClassifier()
articles = classifier.classify_and_filter(articles)
```

---

### `deduplication.py` - Article Deduplication

#### `Deduplicator.deduplicate(articles: List[Article], existing_articles: List[Article] = None) -> Tuple[List[Article], dict]`
Deduplicate articles using exact and fuzzy matching.

**Parameters**:
- `articles` (List[Article]): New articles to process
- `existing_articles` (List[Article], optional): Previously stored articles

**Returns**: Tuple of (unique_articles, stats_dict)

**Stats dict**:
```python
{
    "total_input": 150,
    "url_duplicates": 10,
    "content_hash_duplicates": 5,
    "title_fuzzy_duplicates": 3,
    "unique_output": 132
}
```

**Deduplication Strategy**:
1. Exact URL match (within new and existing)
2. Content hash match across sources
3. Fuzzy title match for same source (85%+ similarity)

**Example**:
```python
dedup = Deduplicator(title_similarity_threshold=0.85)
existing = store.get_recent_articles(limit=1000)
unique, stats = dedup.deduplicate(new_articles, existing)
print(f"Removed {stats['url_duplicates']} duplicates")
```

---

### `persistence.py` - DynamoDB Storage

#### `DynamoDBStore.__init__(table_name: str, region_name: str = "us-east-1")`
Initialize DynamoDB store.

**Parameters**:
- `table_name` (str): DynamoDB table name
- `region_name` (str): AWS region

#### `DynamoDBStore.save_article(article: Article) -> Optional[str]`
Save article to DynamoDB.

**Parameters**:
- `article` (Article): Article to save

**Returns**: Article ID (UUID) or None if error

**Example**:
```python
store = DynamoDBStore("news-articles")
article_id = store.save_article(article)
if article_id:
    print(f"Saved with ID: {article_id}")
```

#### `DynamoDBStore.find_by_url(url: str) -> Optional[StoredArticle]`
Find article by URL.

**Parameters**:
- `url` (str): Article URL

**Returns**: StoredArticle or None

#### `DynamoDBStore.update_article(article_id: str, updates: dict) -> bool`
Update article metadata.

**Parameters**:
- `article_id` (str): UUID from save_article
- `updates` (dict): Dictionary of fields to update

**Example**:
```python
store.update_article(article_id, {
    "last_summary": "New summary text",
    "update_count": 1
})
```

#### `DynamoDBStore.get_recent_articles(limit: int = 100) -> List[StoredArticle]`
Get recent articles.

**Parameters**:
- `limit` (int): Maximum articles to return

**Returns**: List of StoredArticle objects

---

### `summarization.py` - OpenAI Summarization

#### `Summarizer.__init__(api_key: str, model: str = "gpt-4o-mini", max_tokens: int = 300)`
Initialize OpenAI summarizer.

**Parameters**:
- `api_key` (str): OpenAI API key
- `model` (str): Model to use
- `max_tokens` (int): Max tokens in summary

#### `Summarizer.summarize(content: str, title: str = "") -> Optional[str]`
Generate summary of article content.

**Parameters**:
- `content` (str): Article text to summarize
- `title` (str): Article title for context

**Returns**: Summary text or None if error

**Example**:
```python
summarizer = Summarizer(api_key="sk-...")
summary = summarizer.summarize(
    content="Long article text...",
    title="Article Title"
)
print(summary)
```

#### `Summarizer.summarize_update(new_content: str, old_summary: str, title: str = "") -> Optional[str]`
Summarize only the new information in an updated article.

**Parameters**:
- `new_content` (str): Updated article content
- `old_summary` (str): Previous summary
- `title` (str): Article title

**Returns**: Update summary or None

---

### `slack_notifier.py` - Slack Integration

#### `SlackNotifier.__init__(webhook_urls: dict)`
Initialize Slack notifier.

**Parameters**:
- `webhook_urls` (dict): Mapping of topic -> webhook URL
  ```python
  {
      "tech": "https://hooks.slack.com/...",
      "ai": "https://hooks.slack.com/...",
      ...
  }
  ```

#### `SlackNotifier.notify(article: Article, summary: str = "", is_update: bool = False) -> bool`
Send notification for article to appropriate channel(s).

**Parameters**:
- `article` (Article): Article to notify about
- `summary` (str): Summary text
- `is_update` (bool): Whether this is an update

**Returns**: True if successful

**Example**:
```python
notifier = SlackNotifier({
    "tech": "https://hooks.slack.com/...",
    "ai": "https://hooks.slack.com/..."
})
notifier.notify(
    article,
    summary="Brief summary",
    is_update=False
)
```

#### `SlackNotifier.notify_batch(articles: List[Article], summaries: dict = None, is_updates: dict = None) -> bool`
Send notifications for multiple articles.

**Parameters**:
- `articles` (List[Article]): Articles to notify about
- `summaries` (dict): Mapping of URL -> summary text
- `is_updates` (dict): Mapping of URL -> is_update flag

**Returns**: True if all successful

---

### `orchestrator.py` - Main Pipeline

#### `NewsAggregator.__init__(...)`
Initialize the aggregator with all components.

**Parameters**:
- `feed_config_path` (str): Path to feeds.yaml
- `dynamodb_table` (str): DynamoDB table name
- `aws_region` (str): AWS region
- `openai_api_key` (str, optional): OpenAI API key
- `slack_webhooks` (dict, optional): Slack webhook URLs
- `enable_summarization` (bool): Enable OpenAI
- `enable_slack` (bool): Enable Slack notifications
- `max_articles_per_feed` (int): Articles per feed

#### `NewsAggregator.run() -> dict`
Execute the full pipeline.

**Returns**: Stats dictionary
```python
{
    "timestamp": "2024-01-15T10:30:45",
    "feeds_loaded": 10,
    "feeds_processed": 9,
    "articles_ingested": 150,
    "articles_classified": 150,
    "url_duplicates": 10,
    "content_hash_duplicates": 5,
    "title_fuzzy_duplicates": 3,
    "articles_deduplicated": 132,
    "unique_output": 132,
    "articles_saved": 120,
    "articles_summarized": 120,
    "articles_notified": 120,
    "errors": []
}
```

**Example**:
```python
aggregator = NewsAggregator(
    feed_config_path="config/feeds.yaml",
    dynamodb_table="news-articles",
    openai_api_key="sk-...",
    slack_webhooks={...}
)
stats = aggregator.run()
print(f"Processed {stats['articles_saved']} articles")
```

---

## Data Models

### `Article`
Represents a news article.

**Fields**:
```python
title: str                    # Article title
source: str                   # Source domain
url: str                      # Article URL
published_at: datetime        # Original publish time
content: str                  # Article text/summary
topics: List[str]             # Topic tags
content_hash: str             # SHA256 hash
canonical_url: Optional[str]  # Normalized URL
fetched_at: datetime          # When fetched
```

**Methods**:
- `to_dict()` → Dictionary for storage
- `from_dict(dict)` → Create from dictionary

### `StoredArticle` (extends Article)
Article with additional metadata for storage.

**Additional Fields**:
```python
article_id: str               # UUID
first_seen_at: datetime       # First discovery
last_seen_at: datetime        # Last update
last_summary: str             # Cached summary
update_count: int             # Times updated
is_new: bool                  # New vs. update
```

---

## Error Handling

### Common Exceptions
- `FileNotFoundError`: Feed config file not found
- `yaml.YAMLError`: Invalid YAML syntax
- `botocore.exceptions.ClientError`: AWS errors
- `openai.error.OpenAIError`: OpenAI API errors
- `requests.RequestException`: Network errors

### Error Handling Strategy
1. Log detailed error with context
2. Gracefully continue if possible (skip feed, use fallback)
3. Accumulate errors and report at end
4. Never crash pipeline for partial failures

---

## Environment Variables

```python
# AWS
AWS_REGION = "us-east-1"
DYNAMODB_TABLE = "news-articles"

# OpenAI
OPENAI_API_KEY = "sk-..."
OPENAI_MODEL = "gpt-4o-mini"

# Slack
SLACK_WEBHOOK_TECH = "https://hooks.slack.com/..."
SLACK_WEBHOOK_AI = "https://hooks.slack.com/..."
SLACK_WEBHOOK_EDUCATION = "https://hooks.slack.com/..."
SLACK_WEBHOOK_CYBER_SECURITY = "https://hooks.slack.com/..."

# Features
ENABLE_SLACK = true
ENABLE_SUMMARIZATION = true

# Logging
LOG_LEVEL = "INFO"

# Limits
MAX_ARTICLES_PER_FEED = 50
MAX_SUMMARY_LENGTH = 300
```
