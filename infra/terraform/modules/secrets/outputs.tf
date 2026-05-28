# Outputs for Secrets Manager module

output "openai_api_key_arn" {
  description = "OpenAI API key secret ARN"
  value       = aws_secretsmanager_secret.openai_api_key.arn
}

output "slack_webhooks_arn" {
  description = "Slack webhooks secret ARN"
  value       = aws_secretsmanager_secret.slack_webhooks.arn
}
