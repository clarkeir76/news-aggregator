# Terraform variables for news aggregator

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

# Lambda variables
variable "lambda_function_name" {
  description = "Lambda function name"
  type        = string
  default     = "news-aggregator"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "lambda_memory_size" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}

variable "lambda_runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.12"
}

variable "lambda_handler" {
  description = "Lambda handler"
  type        = string
  default     = "lambda_handler.lambda_handler"
}

variable "lambda_source_dir" {
  description = "Path to Lambda source code"
  type        = string
  default     = "../../app"
}

variable "lambda_vpc_config" {
  description = "VPC configuration for Lambda (optional)"
  type = object({
    subnet_ids         = list(string)
    security_group_ids = list(string)
  })
  default = null
}

# DynamoDB variables
variable "dynamodb_table_name" {
  description = "DynamoDB table name"
  type        = string
  default     = "news-articles"
}

variable "dynamodb_read_capacity" {
  description = "DynamoDB read capacity"
  type        = number
  default     = 10
}

variable "dynamodb_write_capacity" {
  description = "DynamoDB write capacity"
  type        = number
  default     = 10
}

# EventBridge variables
variable "eventbridge_schedule" {
  description = "EventBridge schedule expression (cron)"
  type        = string
  default     = "cron(0 */6 * * ? *)"  # Every 6 hours
}

# Application configuration
variable "openai_model" {
  description = "OpenAI model to use"
  type        = string
  default     = "gpt-4o-mini"
}

variable "enable_slack" {
  description = "Enable Slack notifications"
  type        = bool
  default     = true
}

variable "enable_summarization" {
  description = "Enable OpenAI summarization"
  type        = bool
  default     = true
}

variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "INFO"
}

variable "max_articles_per_feed" {
  description = "Maximum articles to fetch per feed"
  type        = number
  default     = 50
}

# Secrets
variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
}

variable "slack_webhook_tech" {
  description = "Slack webhook URL for tech channel"
  type        = string
  sensitive   = true
  default     = ""
}

variable "slack_webhook_ai" {
  description = "Slack webhook URL for AI channel"
  type        = string
  sensitive   = true
  default     = ""
}

variable "slack_webhook_education" {
  description = "Slack webhook URL for education channel"
  type        = string
  sensitive   = true
  default     = ""
}

variable "slack_webhook_cyber_security" {
  description = "Slack webhook URL for cyber security channel"
  type        = string
  sensitive   = true
  default     = ""
}

# Monitoring
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "alarm_actions" {
  description = "SNS topic ARNs for alarms"
  type        = list(string)
  default     = []
}
