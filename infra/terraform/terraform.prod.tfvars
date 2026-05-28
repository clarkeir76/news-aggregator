# Production environment Terraform variables

aws_region     = "us-east-1"
environment    = "prod"

lambda_function_name = "news-aggregator"
lambda_timeout       = 300
lambda_memory_size   = 768

dynamodb_table_name   = "news-articles"
dynamodb_read_capacity  = 20
dynamodb_write_capacity = 20

# Run every 6 hours
eventbridge_schedule = "cron(0 */6 * * ? *)"

enable_slack         = true
enable_summarization = true
log_level            = "INFO"

log_retention_days = 90

# Slack webhook URLs and OpenAI API key must be provided via -var or environment variables
