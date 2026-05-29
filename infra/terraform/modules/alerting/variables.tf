variable "name_prefix" {
  type = string
}

variable "environment" {
  type = string
}

variable "lambda_function_name" {
  description = "Name of the main aggregator Lambda to monitor"
  type        = string
}

variable "slack_alert_webhook" {
  description = "Slack Workflow Builder webhook URL for operational alerts"
  type        = string
  sensitive   = true
}
