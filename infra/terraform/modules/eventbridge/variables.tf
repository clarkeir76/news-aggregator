variable "schedule_name" {
  type = string
}

variable "schedule_expression" {
  type = string
}

variable "environment" {
  type = string
}

variable "lambda_function_arn" {
  type = string
}

variable "lambda_function_name" {
  type = string
}

variable "timezone" {
  description = "IANA timezone for the schedule (e.g. Europe/London)"
  type        = string
  default     = "UTC"
}
