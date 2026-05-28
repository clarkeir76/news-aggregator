# DynamoDB module for news articles storage

resource "aws_dynamodb_table" "articles" {
  name           = var.table_name
  billing_mode   = "PROVISIONED"
  read_capacity  = var.read_capacity
  write_capacity = var.write_capacity
  hash_key       = "pk"
  range_key      = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  # Global Secondary Index for URL lookups
  attribute {
    name = "url_gsi_pk"
    type = "S"
  }

  global_secondary_index {
    name            = "url_index"
    hash_key        = "url_gsi_pk"
    read_capacity   = var.read_capacity
    write_capacity  = var.write_capacity
    projection_type = "ALL"
  }

  # Global Secondary Index for source + date queries
  attribute {
    name = "source_date_gsi_pk"
    type = "S"
  }

  attribute {
    name = "source_date_gsi_sk"
    type = "S"
  }

  global_secondary_index {
    name            = "source_date_index"
    hash_key        = "source_date_gsi_pk"
    range_key       = "source_date_gsi_sk"
    read_capacity   = var.read_capacity
    write_capacity  = var.write_capacity
    projection_type = "ALL"
  }

  # Point-in-time recovery for production
  point_in_time_recovery_specification {
    enabled = var.environment == "prod" ? true : false
  }

  # Encryption at rest
  server_side_encryption_specification {
    enabled     = true
    kms_key_arn = aws_kms_key.dynamodb.arn
  }

  # TTL for old articles (optional)
  ttl {
    attribute_name = "expiration_time"
    enabled        = var.enable_ttl
  }

  stream_specification {
    stream_view_type = "NEW_AND_OLD_IMAGES"
  }

  tags = merge(
    var.tags,
    {
      Name = var.table_name
    }
  )
}

# KMS key for DynamoDB encryption
resource "aws_kms_key" "dynamodb" {
  description             = "KMS key for DynamoDB table ${var.table_name}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = var.tags
}

resource "aws_kms_alias" "dynamodb" {
  name          = "alias/dynamodb-${var.table_name}"
  target_key_id = aws_kms_key.dynamodb.key_id
}

# Auto-scaling for read capacity
resource "aws_appautoscaling_target" "dynamodb_read" {
  max_capacity       = var.max_read_capacity
  min_capacity       = var.read_capacity
  resource_id        = "table/${aws_dynamodb_table.articles.name}"
  scalable_dimension = "dynamodb:table:ReadCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "dynamodb_read_scaling" {
  name               = "dynamodb-${var.table_name}-read-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.dynamodb_read.resource_id
  scalable_dimension = aws_appautoscaling_target.dynamodb_read.scalable_dimension
  service_namespace  = aws_appautoscaling_target.dynamodb_read.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 70.0

    predefined_metric_specification {
      predefined_metric_type = "DynamoDBReadCapacityUtilization"
    }

    scale_out_cooldown  = 60
    scale_in_cooldown   = 300
  }
}

# Auto-scaling for write capacity
resource "aws_appautoscaling_target" "dynamodb_write" {
  max_capacity       = var.max_write_capacity
  min_capacity       = var.write_capacity
  resource_id        = "table/${aws_dynamodb_table.articles.name}"
  scalable_dimension = "dynamodb:table:WriteCapacityUnits"
  service_namespace  = "dynamodb"
}

resource "aws_appautoscaling_policy" "dynamodb_write_scaling" {
  name               = "dynamodb-${var.table_name}-write-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.dynamodb_write.resource_id
  scalable_dimension = aws_appautoscaling_target.dynamodb_write.scalable_dimension
  service_namespace  = aws_appautoscaling_target.dynamodb_write.service_namespace

  target_tracking_scaling_policy_configuration {
    target_value = 70.0

    predefined_metric_specification {
      predefined_metric_type = "DynamoDBWriteCapacityUtilization"
    }

    scale_out_cooldown  = 60
    scale_in_cooldown   = 300
  }
}
