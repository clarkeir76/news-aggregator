# Secrets Manager module

# OpenAI API Key
resource "aws_secretsmanager_secret" "openai_api_key" {
  name                    = "news-aggregator/openai-api-key"
  description             = "OpenAI API key for news aggregator"
  recovery_window_in_days = 7

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "openai_api_key" {
  secret_id     = aws_secretsmanager_secret.openai_api_key.id
  secret_string = var.openai_api_key
}

# Slack Webhooks
resource "aws_secretsmanager_secret" "slack_webhooks" {
  name                    = "news-aggregator/slack-webhooks"
  description             = "Slack webhook URLs for news aggregator"
  recovery_window_in_days = 7

  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "slack_webhooks" {
  secret_id = aws_secretsmanager_secret.slack_webhooks.id
  secret_string = jsonencode({
    tech              = var.slack_webhook_tech
    ai                = var.slack_webhook_ai
    education         = var.slack_webhook_education
    cyber_security    = var.slack_webhook_cyber_security
  })
}

# Grant Lambda access to OpenAI secret
resource "aws_secretsmanager_secret_target_attachment" "lambda_openai" {
  secret_id           = aws_secretsmanager_secret.openai_api_key.id
  target_id           = var.lambda_role_arn
  target_type         = "AWS::Lambda::Function"
}

# Grant Lambda access to Slack secrets
resource "aws_secretsmanager_secret_target_attachment" "lambda_slack" {
  secret_id           = aws_secretsmanager_secret.slack_webhooks.id
  target_id           = var.lambda_role_arn
  target_type         = "AWS::Lambda::Function"
}

# Resource policy for Lambda to read secrets
resource "aws_secretsmanager_resource_policy" "lambda_access" {
  secret_id = aws_secretsmanager_secret.openai_api_key.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = var.lambda_role_arn
        }
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "*"
      }
    ]
  })
}
