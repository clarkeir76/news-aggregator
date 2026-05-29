aws_region  = "eu-west-1"
environment = "prod"

lambda_timeout     = 300
lambda_memory_size = 768
# lambda_s3_bucket and lambda_s3_key passed via -var in CI

eventbridge_schedule = "cron(0 */1 * * ? *)"

enable_slack          = true
enable_summarization  = true
log_level             = "INFO"
max_articles_per_feed = 50
log_retention_days    = 90
