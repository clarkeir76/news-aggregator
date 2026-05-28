# Development environment Terraform variables

aws_region     = "us-east-1"
environment    = "dev"

lambda_function_name = "news-aggregator-dev"
lambda_timeout       = 300
lambda_memory_size   = 512

dynamodb_table_name   = "news-articles-dev"
dynamodb_read_capacity  = 5
dynamodb_write_capacity = 5

eventbridge_schedule = "cron(0 12 * * ? *)"  # Daily at noon

enable_slack         = false
enable_summarization = false
log_level            = "DEBUG"

log_retention_days = 7

# Note: openai_api_key must be provided via -var or environment variable
# export TF_VAR_openai_api_key="sk-..."
