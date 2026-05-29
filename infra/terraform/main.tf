terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Bucket and key are passed via -backend-config in CI so the same config
  # works for test-{run-id}, dev, and prod without code changes.
  backend "s3" {
    region  = "eu-west-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "news-aggregator"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

locals {
  name_prefix = "news-aggregator-${var.environment}"
}

module "dynamodb" {
  source      = "./modules/dynamodb"
  table_name  = "${local.name_prefix}-articles"
  environment = var.environment
}

module "lambda" {
  source        = "./modules/lambda"
  function_name = local.name_prefix
  environment   = var.environment

  lambda_s3_bucket = var.lambda_s3_bucket
  lambda_s3_key    = var.lambda_s3_key

  dynamodb_table_arn  = module.dynamodb.table_arn
  dynamodb_table_name = module.dynamodb.table_name

  environment_variables = {
    DYNAMODB_TABLE               = module.dynamodb.table_name
    OPENAI_API_KEY               = var.openai_api_key
    OPENAI_MODEL                 = var.openai_model
    ENABLE_SLACK                 = tostring(var.enable_slack)
    ENABLE_SUMMARIZATION         = tostring(var.enable_summarization)
    ENABLE_PERSISTENCE           = "true"
    ENABLE_LLM_CLASSIFICATION    = "true"
    LOG_LEVEL                    = var.log_level
    MAX_ARTICLES_PER_FEED        = tostring(var.max_articles_per_feed)
    MAX_CONCURRENT_FEEDS         = "10"
    FEED_CONFIG_PATH             = "/opt/config/feeds.yaml"
    SLACK_WEBHOOK_TECH           = var.slack_webhook_tech
    SLACK_WEBHOOK_AI             = var.slack_webhook_ai
    SLACK_WEBHOOK_EDUCATION      = var.slack_webhook_education
    SLACK_WEBHOOK_CYBER_SECURITY = var.slack_webhook_cyber_security
  }

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory_size
}

module "eventbridge" {
  source               = "./modules/eventbridge"
  schedule_name        = "${local.name_prefix}-schedule"
  schedule_expression  = var.eventbridge_schedule
  environment          = var.environment
  lambda_function_arn  = module.lambda.function_arn
  lambda_function_name = module.lambda.function_name
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${module.lambda.function_name}"
  retention_in_days = var.log_retention_days
}
