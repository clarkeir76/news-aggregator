# Design Decisions

Key decisions and the reasoning behind them.

---

## Classify before fetching article content

**Decision**: RSS title and summary are classified by the LLM before any full article text is fetched. Only articles that match a topic have their full text retrieved.

**Why**: Fetching full article text is slow (one HTTP request per article, often with JS-heavy sites). Running it on every article before knowing whether we care about it wastes most of that time — typical runs see ~70% of articles discarded at classification. Classifying on RSS content first (which is free — already in the feed) means article fetching only happens for the ~30% that matters.

**Trade-off**: Classification accuracy is slightly lower without full article text, since it relies on RSS titles and summaries. In practice this is acceptable — titles and summaries describe the topic well enough for filtering purposes, and any edge cases are caught in subsequent runs.

---

## Story clustering: same-event grouping vs same-theme separation

**Decision**: The clustering prompt groups articles about the *exact same specific event* (same lawsuit, breach, launch, report) — including different headline angles or framings of that event — but does not group articles that merely share a topic or theme. There is no per-cluster article cap. The prompt requires the articles to report the same specific launch, incident, announcement, result or report: sharing a company, person or theme is not enough (two articles that both mention Anthropic are different stories). When unsure the LLM keeps them separate, but clear event matches are grouped whatever the framing or article type.

**Why**: An earlier version had a "max 3 articles per group" cap and a "when in doubt, keep separate" rule. This caused stories covered by 4–6 outlets to be split into multiple clusters representing the same underlying event (e.g. 6 articles about a single Florida/OpenAI lawsuit producing two clusters with different headline angles). Fuzzy string matching cannot reliably catch these as duplicates post-clustering (different framings score ~52% similarity, while genuinely different stories on the same topic score ~68%), so the fix must be at the clustering stage. The "do not group thematically related articles" rule remains to prevent over-clustering. A later version of the "when in doubt, group" rule combined with summary snippets and an "analysis counts as the same story" rule over-merged on a 60-article run (merging a Mistral cybersecurity model release into a Google Gemini story, and an unrelated Pentagon AI-agent story into a Claude exploit story). Because the significance threshold is applied after clustering using the best score in each cluster, a wrong merge also lifts weak articles into the digest, so a shared-event requirement was added (a first attempt at "same company" still merged an Anthropic research story with an Anthropic hiring story), RSS summary snippets are stripped of HTML before use, and multi-member clusters are logged at INFO. Clustering and scoring were judged markedly better on `gpt-4.1` than `gpt-4o-mini`, so set `CLASSIFY_MODEL` and `CLUSTER_MODEL` to it in production.

## LLM classification with reader-specific criteria

**Decision**: The classification prompt includes explicit include/exclude criteria per topic, originally calibrated for a UK software engineering leader in the post-18 education sector (see "Strategic significance scoring" below for the current persona). Topic descriptions define not just what to include but what to actively exclude (e.g. consumer tech deals for `tech`, primary school stories for `education`). The system prompt identifies the reader role so the LLM can make relevance judgements at the right level.

**Why**: Generic topic descriptions (e.g. "technology, software, startups") produce too many irrelevant articles (consumer gadget deals, gaming, school disaster stories). Explicit exclusion criteria significantly improve signal-to-noise without needing per-feed topic pre-assignment.

## Strategic significance scoring and AI-as-subject rule

**Decision**: The LLM classifier returns a 1–5 significance score alongside topics, and articles below `MIN_SIGNIFICANCE` (default 4) are discarded. The `ai` topic description is written around strategic significance (frontier model releases, breakthroughs, major company moves, policy, large-scale impact; AI in education only when strategic) and requires AI to be the article's primary subject. Incremental updates, individual papers, anecdotes and stories where AI or an AI executive is incidental are explicitly excluded. The reader persona is a senior technology leader in education wanting what peers will be discussing. General-news feeds and the arXiv cs.AI feed are disabled.

**Why**: A topic-match yes/no with "cast a wide net" produced niche and incremental stories, and let through stories that merely involved someone in AI (e.g. espionage targeting a chip company CEO). A score makes selectivity tunable through an env var rather than by rewording prompts. The "classify before fetching" rule is unchanged — the score comes from the same batch call. The keyword fallback has no score and is unaffected.

A first dry run with only "4 or above" kept 30 stories a day, including webinar promotions and vendor tool announcements, because small models inflate scores. The prompt now calibrates harshly (most matches score 2-3, about 1 in 20 scores 4-5, and webinars, promotion, vendor announcements, opinion, case studies and non-AI partnerships score at most 2), and every kept/dropped decision with its score is logged at INFO so the threshold can be tuned from data.

An attempt to include "market-moving AI business news" (earnings, share prices, capex) at score 4 backfired: the first production digest was three financial-market stories (AWS accelerator revenue, Alphabet's search revenue, Microsoft's $25B debt raise). The reader wants what AI can newly do (model releases, breakthroughs, groundbreaking uses) ahead of the finances of AI companies, so routine financial-market stories are now excluded from the topic and capped at a score of 3 (below the default threshold) unless the story itself changes the AI landscape.

The same dry run showed per-article scores varied between outlets covering the same story (e.g. 5, 5 and 4 for one model launch), and a threshold applied per article dropped the lower-scoring member before it could join its cluster. The threshold is therefore applied after clustering, on the highest score in each cluster (`filter_by_significance`), and `CLASSIFY_MODEL` allows a stronger model for scoring consistency. Classification still happens before content fetching; clustering now runs on all topic-matched articles (roughly 80 titles rather than ~30), which remains a single cheap call.

---

## Clustering inputs, URL pre-dedupe and a separate clustering model

**Decision**: (1) Exact-URL repeats are removed straight after ingestion, before classification. (2) The clustering prompt includes a 200-character RSS summary snippet per article and states that analysis, review or opinion pieces about the same launch or announcement belong in the same group as the news reports. (3) `CLUSTER_MODEL` optionally sets a different model for clustering only. (4) `OPENAI_MODEL` is now actually passed to the classifier and summariser (previously it was read into config but ignored).

**Why**: The same article arriving via two overlapping feeds (e.g. TechCrunch's main and AI feeds) was classified twice, clustered with itself and shown as "multiple sources" with a repeated link. Title-only clustering missed same-story pieces with different framing (a model announcement vs a "looks like a diamond in the rough" review); snippets give shared names and products to match on. Clustering is one call per run, so a stronger model there is cheap. Cluster members' significance scores are merged (max) so the digest can be ordered by importance.

---

## LLM classification with keyword fallback

**Decision**: `LLMClassifier` is the default. `KeywordClassifier` is used as a fallback when the API call fails, or when `ENABLE_LLM_CLASSIFICATION=false`.

**Why LLM over keywords**:
- Better accuracy — understands context, not just word presence
- Can reject articles (keywords have no confidence in rejection)
- A single batched API call covers all articles, so cost is low (~$0.001–0.005 per run)
- Handles nuance — "university suffers ransomware attack" correctly maps to both `education` and `cyber_security`; pure keyword matching struggles with this

**Why keep keywords as fallback**:
- Protects against API outages
- Predictable, deterministic behaviour for debugging
- Zero cost if LLM is unavailable

---

## Single batched LLM call for classification

**Decision**: All article titles and summaries for a given run are sent to the LLM in one API call, not one call per article.

**Why**: Per-article calls would add 0.5–1s per article and multiply API costs. With 48 feeds × 5 articles = 240 articles, per-article calls would take 2–4 minutes just for classification. A single batch call takes 5–15 seconds regardless of article count and costs roughly the same as a handful of individual calls.

---

## trafilatura for full article extraction

**Decision**: Use `trafilatura` to extract main article text from HTML pages when RSS content is insufficient.

**Why over alternatives**:
- Built on Mozilla's readability algorithm — handles diverse page layouts well
- Actively maintained
- Handles encoding, boilerplate removal and link stripping automatically
- Graceful failure — returns `None` if it can't extract, letting the pipeline continue with RSS summary

**Limitation**: Cannot handle JavaScript-rendered pages or paywalled content. These fall back to using the RSS summary.

---

## Concurrent feed fetching and content enrichment

**Decision**: Both feed fetching (`ingest_feeds`) and article content enrichment (`_enrich_content`) use `ThreadPoolExecutor` with a configurable worker count (`MAX_CONCURRENT_FEEDS`, default 10).

**Why threads over async**:
- The bottleneck is network I/O — threads spend most time waiting, so CPU contention is minimal
- No rewrite needed — `feedparser`, `trafilatura`, and `requests` are all synchronous
- `ThreadPoolExecutor` is simple, well-understood, and handles errors gracefully

**Why not multiprocessing**: Overhead of process creation outweighs benefits at this scale. The GIL is not a meaningful constraint for I/O-bound work.

---

## Slack digest payload limits

**Decision**: Digests are capped at 10 articles per channel (ordered by significance score, highest first, so cap and truncation drop the least significant stories) and the payload string is truncated to 7,800 characters. When the cap is exceeded an "… and N more" line is appended; when the character limit is hit a "… truncated" notice is added.

**Why**: Slack Workflow Builder has an undocumented payload size limit (~8,000 chars). Oversized payloads are silently accepted (200 response) but never posted. This caused tech/AI/cyber digests to disappear on high-volume runs while education (fewer articles) still worked. The cap and truncation ensure messages always arrive.

## Slack Workflow Builder webhooks with plain text

**Decision**: Use Slack Workflow Builder trigger URLs and send a flat `payload` string variable. No markdown or Block Kit formatting.

**Why**: Workflow Builder triggers treat message content as plain text — mrkdwn and Block Kit formatting do not render reliably. Plain text with bare URLs works correctly: Slack auto-links URLs, making them clickable without any special syntax.

**One digest per topic per run**: Rather than posting one message per article, all matched articles for a topic are bundled into a single message per run. This prevents channel flooding and gives readers a clear "here's what happened" snapshot.

---

## Vector embeddings for RAG (ENABLE_EMBEDDINGS)

**Decision**: Article embeddings are generated using OpenAI `text-embedding-3-small` (1536 dimensions) from `title + summary` and stored in Qdrant. The step runs after summarisation so the full context is available. Point IDs are deterministic (UUID5 of article URL) so re-runs are idempotent.

**Why title + summary rather than full content**: Summaries are already generated, concise, and represent the article well for semantic search. Full content would be expensive and often noisier.

**Why Qdrant on ECS rather than DynamoDB**: DynamoDB doesn't support approximate nearest-neighbour search. Qdrant is purpose-built for vector search and will host the query interface. At this scale (few thousand articles with 14-day TTL) a single Qdrant container is sufficient.

**Why feature-flagged**: The RAG query interface (chatbot UI) isn't built yet. The embedding step is additive with no risk to the existing pipeline, but is disabled in prod until the interface is ready and tested.

## Data retention

**DynamoDB TTL**: Articles are automatically deleted 14 days after they are saved, via DynamoDB's TTL feature (`expiration_time` Unix timestamp). This prevents unbounded growth while keeping enough history for deduplication across a typical working week. Articles older than 14 days would never be surfaced as "new" anyway given `MAX_ARTICLE_AGE_HOURS=60`.

**S3 Lambda packages**: Each CI run uploads a new Lambda package under `lambda-packages/{run-id}/`. An S3 lifecycle policy expires these objects after 30 days. Terraform state files are unaffected — they have no expiry.

## DynamoDB partition key conventions

Article records use `pk = ARTICLE#{uuid}`, system records use `pk = SYSTEM#config`. The `get_recent_articles()` scan filters to `ARTICLE#` keys only — this prevents system records (e.g. `last_run` timestamps) from being passed to `StoredArticle.from_dict()` and crashing.

## DynamoDB for persistence

**Decision**: DynamoDB with a simple `ARTICLE#{uuid}` / `METADATA` key scheme and two GSIs.

**Why over relational databases**:
- Serverless — no infrastructure to manage
- Pay-per-request pricing suits batch workloads
- GSIs provide URL and source/date lookups without complex joins

**SK design**: The sort key is the static string `"METADATA"` rather than a timestamp. This means `get_item` and `update_item` can address any article by its UUID without needing to know when it was created.

---

## Three-layer deduplication

**Decision**: URL match → content hash → fuzzy title (≥85% similarity, same source only).

**Why this order**: URL matching is O(1) and eliminates the most obvious duplicates. Content hashing catches identical articles reposted at different URLs. Fuzzy matching is most expensive (O(n²) against existing articles) so runs last.

**Why fuzzy match is source-restricted**: Two different publications with similar headlines are not duplicates — they're independent coverage of the same story and should both appear. Fuzzy matching only applies within the same source domain.

**Threshold at 85%**: Chosen to catch clear near-duplicates (minor edits to the same article) while avoiding false positives between genuinely different articles from the same source.

---

## Structured JSON logging

**Decision**: All logs are JSON-formatted. Locally, logs write to both stdout and `logs/run.log`. In Lambda, stdout only (CloudWatch captures it).

**Why JSON**: Parseable by CloudWatch Logs Insights and any log aggregation tool. Field-based queries ("show me all ERROR logs from ingestion in the last hour") are possible without regex.

**File logging locally**: Means the log file can be read directly without pasting terminal output. The file path is configurable via `LOG_FILE` and disabled automatically in Lambda (detected via `AWS_LAMBDA_FUNCTION_NAME`).

---

## Topic selection via ENABLED_TOPICS

**Decision**: `ENABLED_TOPICS` (comma-separated, default all) restricts which topics are classified. Disabled topics are removed from the LLM prompt and keyword matching, so articles that only fit a disabled topic are discarded at classification.

**Why**: Removing a Slack webhook only silences the digest — the pipeline would still spend LLM tokens, fetch full article text and persist articles for topics nobody reads. Filtering at classification keeps the "classify before fetching" rule. Re-enabling a topic is an env var change, not a code change. When `tech` is disabled the keyword fallback no longer defaults unmatched articles to `tech`; they are dropped.

---

## Lambda package size: split requirements

**Decision**: `requirements.txt` holds runtime dependencies only. `requirements-dev.txt` adds boto3/botocore and the test/lint tools for local and CI use. The Lambda zip is built from `requirements.txt`.

**Why**: Adding `qdrant-client` (which pulls in grpcio, numpy and pydantic) pushed the unzipped package past Lambda's 250 MB limit, so CI failed at Terraform Apply and nothing deployed after 1 June 2026. The package had also been carrying mypy, black, flake8, pytest and a pinned boto3 that the Lambda runtime already provides. If the package approaches the limit again, make `qdrant-client` an optional import or move to a container image.

---

## Feature flags via environment variables

**Decision**: All major features (`ENABLE_SLACK`, `ENABLE_SUMMARIZATION`, `ENABLE_PERSISTENCE`, `ENABLE_LLM_CLASSIFICATION`) are controlled by environment variables with sensible defaults.

**Why**: Enables four distinct testing modes without code changes:
1. No AWS, no Slack — fastest local test
2. `ENABLE_SLACK=log` — see what would be posted without actually posting
3. LocalStack — full pipeline with local DynamoDB
4. Production AWS — full pipeline

Each mode is a single `.env` change.

---

## Pre-commit test hook

**Decision**: `tests/` runs automatically on every `git commit` via a pre-commit hook. The commit is blocked if any test fails.

**Why**: Prevents broken code from reaching the repo. The test suite runs in under 3 seconds (all mocked), so the overhead is negligible. `git commit --no-verify` is available if you genuinely need to bypass it.
