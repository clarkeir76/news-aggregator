aws_region  = "eu-west-1"
environment = "dev"

lambda_timeout     = 300
lambda_memory_size = 512
# lambda_s3_bucket and lambda_s3_key passed via -var in CI

eventbridge_schedule = "cron(0 12 * * ? *)"

enable_slack          = false
enable_summarization  = true
log_level             = "DEBUG"
max_articles_per_feed = 5
log_retention_days    = 7
