# Terraform outputs for news aggregator

output "lambda_function_arn" {
  description = "Lambda function ARN"
  value       = module.lambda.function_arn
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = module.lambda.function_name
}

output "dynamodb_table_name" {
  description = "DynamoDB table name"
  value       = module.dynamodb.table_name
}

output "dynamodb_table_arn" {
  description = "DynamoDB table ARN"
  value       = module.dynamodb.table_arn
}

output "eventbridge_schedule_arn" {
  description = "EventBridge schedule ARN"
  value       = module.eventbridge.schedule_arn
}

output "cloudwatch_log_group_name" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "secrets_openai_api_key_arn" {
  description = "Secrets Manager OpenAI API key ARN"
  value       = module.secrets.openai_api_key_arn
  sensitive   = true
}

output "secrets_slack_webhooks_arn" {
  description = "Secrets Manager Slack webhooks ARN"
  value       = module.secrets.slack_webhooks_arn
  sensitive   = true
}

output "deployment_info" {
  description = "Deployment information"
  value = {
    environment           = var.environment
    region                = var.aws_region
    lambda_function_name  = module.lambda.function_name
    dynamodb_table_name   = module.dynamodb.table_name
    schedule              = var.eventbridge_schedule
  }
}
