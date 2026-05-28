# CLAUDE.md — News Aggregator

Instructions for Claude Code when working in this repository.

## Before Committing

After making any code changes, always check and update before committing — never leave as a follow-up:

1. **Tests** — Do any existing tests need updating? Is there missing coverage for new behaviour? Run `venv/bin/pytest tests/ -v` to confirm all pass.
2. **README.md** — Does the pipeline description, env vars table, or any other section need updating?
3. **ARCHITECTURE.md** — Does the pipeline diagram or data flow description still match the code?
4. **DESIGN_DECISIONS.md** — Does any decision need updating or a new one documenting?
5. **DEPLOYMENT.md** — Are all environment variables in the Lambda setup section current?
6. **API.md** — Do any function signatures or module descriptions need updating?

## Using --no-verify

`git commit --no-verify` MUST ONLY be used for commits with type `style:` (pure auto-formatting, zero behaviour change — e.g. running `black`).

NEVER use `--no-verify` for `feat:`, `fix:`, `refactor:`, `docs:`, or any other commit type. The CI pipeline will fail the build if Python files change without corresponding `.md` updates (unless the commit message starts with `style:`). There is no way to bypass this.

## Pipeline Overview

```
ingest (RSS title + summary, concurrent)
  → LLM batch classify + filter (one API call)
    → fetch full article text (concurrent, matched articles only)
      → deduplicate → persist (DynamoDB, optional) → summarise → Slack digest
```

## Key Design Rules

- Classification happens before content fetching — never move expensive operations earlier in the pipeline
- Both `LLMClassifier` and `KeywordClassifier` implement `classify_and_filter(articles)` — keep this interface consistent
- `ContentExtractor` is called from `orchestrator._enrich_content()`, not from ingestion
- All feature flags are environment variables — no code changes needed to switch modes
- Tests mock all external dependencies (OpenAI, Slack, DynamoDB, feedparser, trafilatura)
- Smoke tests in `test_smoke.py` do NOT mock — they test real library initialisation

## Environment

- Python virtual environment: `venv/`
- Activate: `source venv/bin/activate`
- Run locally: `python app/lambda_handler.py`
- Run tests: `venv/bin/pytest tests/ -v`
- Logs written to: `logs/run.log` (locally)

## Topics

The four supported topics are `tech`, `ai`, `cyber_security`, `education`. These are defined in `models.py` as `Topic` enum values and referenced in `classification.py` `TOPICS` dict. Adding a new topic requires changes in both places plus a new Slack webhook.
