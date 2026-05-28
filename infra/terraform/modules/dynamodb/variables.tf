# Variables for DynamoDB module

variable "table_name" {
  description = "DynamoDB table name"
  type        = string
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
}

variable "read_capacity" {
  description = "Initial read capacity units"
  type        = number
  default     = 10
}

variable "write_capacity" {
  description = "Initial write capacity units"
  type        = number
  default     = 10
}

variable "max_read_capacity" {
  description = "Maximum read capacity for auto-scaling"
  type        = number
  default     = 100
}

variable "max_write_capacity" {
  description = "Maximum write capacity for auto-scaling"
  type        = number
  default     = 100
}

variable "enable_ttl" {
  description = "Enable TTL for old articles"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply"
  type        = map(string)
  default     = {}
}
