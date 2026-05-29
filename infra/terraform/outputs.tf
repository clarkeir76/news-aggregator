output "lambda_function_name" {
  value = module.lambda.function_name
}

output "lambda_function_arn" {
  value = module.lambda.function_arn
}

output "dynamodb_table_name" {
  value = module.dynamodb.table_name
}

output "environment" {
  value = var.environment
}
