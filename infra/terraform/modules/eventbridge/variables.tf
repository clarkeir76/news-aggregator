# Variables for EventBridge module

variable "schedule_name" {
  description = "EventBridge schedule name"
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge cron expression"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "lambda_function_arn" {
  description = "Lambda function ARN"
  type        = string
}

variable "lambda_function_name" {
  description = "Lambda function name"
  type        = string
}

variable "tags" {
  description = "Tags to apply"
  type        = map(string)
  default     = {}
}
