# EventBridge module for scheduling Lambda

resource "aws_scheduler_schedule" "lambda_trigger" {
  name                = var.schedule_name
  description         = "Trigger news aggregator Lambda function"
  schedule_expression = var.schedule_expression
  timezone            = "UTC"
  state               = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = var.lambda_function_arn
    role_arn = aws_iam_role.eventbridge.arn

    retry_policy {
      maximum_attempts       = 2
      maximum_event_age      = 3600  # 1 hour
    }

    dead_letter_config {
      arn = aws_sqs_queue.dlq.arn
    }
  }
}

# IAM role for EventBridge
resource "aws_iam_role" "eventbridge" {
  name = "${var.schedule_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

# Policy to invoke Lambda
resource "aws_iam_role_policy" "eventbridge_lambda" {
  name = "${var.schedule_name}-lambda-policy"
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = var.lambda_function_arn
      }
    ]
  })
}

# Policy to send to SQS DLQ
resource "aws_iam_role_policy" "eventbridge_dlq" {
  name = "${var.schedule_name}-dlq-policy"
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.dlq.arn
      }
    ]
  })
}

# Dead Letter Queue
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.lambda_function_name}-dlq"
  message_retention_seconds = 1209600  # 14 days

  tags = var.tags
}
