output "table_name" {
  value = aws_dynamodb_table.articles.name
}

output "table_arn" {
  value = aws_dynamodb_table.articles.arn
}
