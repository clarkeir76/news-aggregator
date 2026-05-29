variable "function_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "lambda_s3_bucket" {
  type = string
}

variable "lambda_s3_key" {
  type = string
}

variable "dynamodb_table_arn" {
  type = string
}

variable "dynamodb_table_name" {
  type = string
}

variable "environment_variables" {
  type    = map(string)
  default = {}
}

variable "timeout" {
  type    = number
  default = 300
}

variable "memory_size" {
  type    = number
  default = 512
}
