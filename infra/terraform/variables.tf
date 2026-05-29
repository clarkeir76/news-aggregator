variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-west-1"
}

variable "environment" {
  description = "Environment name — prod, dev, or ephemeral test-{run-id}"
  type        = string
}

# Lambda
variable "lambda_timeout" {
  type    = number
  default = 300
}

variable "lambda_memory_size" {
  type    = number
  default = 512
}

variable "lambda_s3_bucket" {
  description = "S3 bucket containing the Lambda deployment package"
  type        = string
}

variable "lambda_s3_key" {
  description = "S3 key for the Lambda deployment package"
  type        = string
}

# EventBridge
variable "eventbridge_schedule" {
  description = "EventBridge cron schedule expression"
  type        = string
  default     = "cron(0 */6 * * ? *)"
}

# Application
variable "openai_model" {
  type    = string
  default = "gpt-4o-mini"
}

variable "enable_slack" {
  type    = bool
  default = false
}

variable "enable_summarization" {
  type    = bool
  default = true
}

variable "log_level" {
  type    = string
  default = "INFO"
}

variable "max_articles_per_feed" {
  type    = number
  default = 50
}

variable "max_summary_length" {
  type    = number
  default = 300
}

variable "max_concurrent_feeds" {
  type    = number
  default = 10
}

variable "max_concurrent_summarizations" {
  type    = number
  default = 5
}

variable "max_article_age_hours" {
  type    = number
  default = 24
}

variable "feed_timeout" {
  type    = number
  default = 20
}

variable "log_retention_days" {
  type    = number
  default = 30
}

# Secrets — passed via GitHub Secrets in CI, never hardcoded
variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "slack_webhook_tech" {
  type      = string
  sensitive = true
  default   = ""
}

variable "slack_webhook_ai" {
  type      = string
  sensitive = true
  default   = ""
}

variable "slack_webhook_education" {
  type      = string
  sensitive = true
  default   = ""
}

variable "slack_webhook_cyber_security" {
  type      = string
  sensitive = true
  default   = ""
}

variable "slack_alert_webhook" {
  description = "Slack webhook for operational alerts (errors, timeouts, missed runs). Leave empty to disable alerting."
  type        = string
  sensitive   = true
  default     = ""
}
