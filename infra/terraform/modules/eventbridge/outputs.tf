# Outputs for EventBridge module

output "schedule_arn" {
  description = "EventBridge schedule ARN"
  value       = aws_scheduler_schedule.lambda_trigger.arn
}

output "schedule_name" {
  description = "EventBridge schedule name"
  value       = aws_scheduler_schedule.lambda_trigger.name
}

output "dlq_arn" {
  description = "Dead Letter Queue ARN"
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "Dead Letter Queue URL"
  value       = aws_sqs_queue.dlq.url
}
