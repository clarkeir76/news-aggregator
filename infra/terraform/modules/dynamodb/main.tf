resource "aws_dynamodb_table" "articles" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "url_gsi_pk"
    type = "S"
  }

  global_secondary_index {
    name            = "url_index"
    hash_key        = "url_gsi_pk"
    projection_type = "ALL"
  }

  # TTL — DynamoDB auto-deletes articles when expiration_time passes
  ttl {
    attribute_name = "expiration_time"
    enabled        = true
  }

  # Point-in-time recovery for prod only
  point_in_time_recovery {
    enabled = var.environment == "prod"
  }

  tags = {
    Name = var.table_name
  }
}
