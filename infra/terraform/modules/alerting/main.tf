# Package the handler into a zip
data "archive_file" "handler" {
  type        = "zip"
  source_file = "${path.module}/handler.py"
  output_path = "${path.module}/handler.zip"
}

# IAM role for the alerting Lambda
resource "aws_iam_role" "alerting" {
  name = "${var.name_prefix}-alerting-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.alerting.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Alerting Lambda
resource "aws_lambda_function" "alerting" {
  function_name    = "${var.name_prefix}-alerting"
  role             = aws_iam_role.alerting.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 30
  filename         = data.archive_file.handler.output_path
  source_code_hash = data.archive_file.handler.output_base64sha256

  environment {
    variables = {
      SLACK_WEBHOOK_URL = var.slack_alert_webhook
      ENVIRONMENT       = var.environment
    }
  }
}

# SNS topic for alarms
resource "aws_sns_topic" "alarms" {
  name = "${var.name_prefix}-alarms"
}

# Allow SNS to invoke the alerting Lambda
resource "aws_lambda_permission" "sns" {
  statement_id  = "AllowSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.alerting.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.alarms.arn
}

# Subscribe the Lambda to the SNS topic
resource "aws_sns_topic_subscription" "lambda" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.alerting.arn
}

# Alarm: any Lambda errors
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.name_prefix}-errors"
  alarm_description   = "Lambda returned an error"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# Alarm: Lambda approaching timeout (>4.5 min average)
resource "aws_cloudwatch_metric_alarm" "duration" {
  alarm_name          = "${var.name_prefix}-duration"
  alarm_description   = "Lambda duration approaching 5 minute timeout"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Maximum"
  threshold           = 270000 # 4.5 minutes in milliseconds
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# Alarm: no invocations for 70 consecutive hours
# Schedule is 8am/12pm/4pm weekdays (Europe/London).
# Longest legitimate gap: Friday 4pm → Monday 8am = 64 hours.
# 70 hours means the alarm only fires if Lambda misses the Monday 8am run
# AND the Monday 12pm run — i.e. something is genuinely broken, not just
# overnight or a weekend.
resource "aws_cloudwatch_metric_alarm" "no_invocations" {
  alarm_name          = "${var.name_prefix}-no-invocations"
  alarm_description   = "Lambda has not been invoked in 70 hours — EventBridge may have stopped"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 70
  metric_name         = "Invocations"
  namespace           = "AWS/Lambda"
  period              = 3600 # 1 hour × 70 = 70 hours total
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "breaching"

  dimensions = {
    FunctionName = var.lambda_function_name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}
