output "schedule_arn" {
  value = aws_scheduler_schedule.main.arn
}

output "schedule_name" {
  value = aws_scheduler_schedule.main.name
}
