# Terraform configuration for news aggregator infrastructure

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Configure remote state (update S3 bucket name)
  backend "s3" {
    bucket         = "news-aggregator-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "news-aggregator"
      Environment = var.environment
      ManagedBy   = "Terraform"
      CreatedAt   = timestamp()
    }
  }
}

# DynamoDB table for articles
module "dynamodb" {
  source = "./modules/dynamodb"

  table_name = var.dynamodb_table_name
  environment = var.environment

  # Auto-scaling configuration
  read_capacity  = var.dynamodb_read_capacity
  write_capacity = var.dynamodb_write_capacity

  tags = local.common_tags
}

# Lambda function for news aggregation
module "lambda" {
  source = "./modules/lambda"

  function_name = var.lambda_function_name
  environment   = var.environment

  # Lambda configuration
  timeout         = var.lambda_timeout
  memory_size     = var.lambda_memory_size
  runtime         = var.lambda_runtime
  handler         = var.lambda_handler
  source_dir      = var.lambda_source_dir
  source_hash     = filebase64sha256("${var.lambda_source_dir}/lambda_handler.py")

  # Environment variables
  environment_variables = {
    DYNAMODB_TABLE     = module.dynamodb.table_name
    AWS_REGION         = var.aws_region
    OPENAI_MODEL       = var.openai_model
    ENABLE_SLACK       = var.enable_slack
    ENABLE_SUMMARIZATION = var.enable_summarization
    LOG_LEVEL          = var.log_level
    MAX_ARTICLES_PER_FEED = var.max_articles_per_feed
  }

  # VPC configuration (optional)
  vpc_config = var.lambda_vpc_config

  # DynamoDB permissions
  dynamodb_table_arn = module.dynamodb.table_arn

  tags = local.common_tags

  depends_on = [module.dynamodb]
}

# EventBridge scheduler for Lambda
module "eventbridge" {
  source = "./modules/eventbridge"

  schedule_name    = "${var.lambda_function_name}-schedule"
  schedule_expression = var.eventbridge_schedule
  environment      = var.environment

  # Lambda target
  lambda_function_arn = module.lambda.function_arn
  lambda_function_name = module.lambda.function_name

  tags = local.common_tags

  depends_on = [module.lambda]
}

# Secrets Manager for sensitive configuration
module "secrets" {
  source = "./modules/secrets"

  environment = var.environment

  # Secret values (from variables)
  openai_api_key        = var.openai_api_key
  slack_webhook_tech    = var.slack_webhook_tech
  slack_webhook_ai      = var.slack_webhook_ai
  slack_webhook_education = var.slack_webhook_education
  slack_webhook_cyber_security = var.slack_webhook_cyber_security

  lambda_role_arn = module.lambda.role_arn

  tags = local.common_tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${module.lambda.function_name}"
  retention_in_days = var.log_retention_days

  tags = local.common_tags
}

# CloudWatch alarms
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.lambda_function_name}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5

  dimensions = {
    FunctionName = module.lambda.function_name
  }

  alarm_description = "Alert when Lambda errors exceed threshold"
  alarm_actions     = var.alarm_actions

  tags = local.common_tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  alarm_name          = "${var.lambda_function_name}-duration"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Average"
  threshold           = 50000  # 50 seconds

  dimensions = {
    FunctionName = module.lambda.function_name
  }

  alarm_description = "Alert when Lambda execution time exceeds threshold"
  alarm_actions     = var.alarm_actions

  tags = local.common_tags
}

# CloudWatch Dashboard
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "news-aggregator-${var.environment}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", { stat = "Sum" }],
            [".", "Errors", { stat = "Sum" }],
            [".", "Duration", { stat = "Average" }],
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", { stat = "Sum" }],
            [".", "ConsumedReadCapacityUnits", { stat = "Sum" }],
          ]
          period = 300
          stat   = "Sum"
          region = var.aws_region
          title  = "News Aggregator Metrics"
        }
      }
    ]
  })
}

locals {
  common_tags = {
    Project     = "news-aggregator"
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}
