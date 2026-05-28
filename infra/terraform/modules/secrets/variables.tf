# Variables for Secrets Manager module

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

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

variable "lambda_role_arn" {
  description = "Lambda execution role ARN"
  type        = string
}

variable "tags" {
  description = "Tags to apply"
  type        = map(string)
  default     = {}
}
