# Used for ephemeral CI test environments.
# environment and lambda_s3_* are passed via -var in the pipeline.
aws_region = "eu-west-1"

lambda_timeout     = 300
lambda_memory_size = 1024

eventbridge_schedule = "cron(0 0 1 1 ? 2099)" # Effectively disabled — triggered manually in CI

enable_slack          = false
enable_summarization  = true
log_level             = "INFO"
max_articles_per_feed = 2
log_retention_days    = 1
