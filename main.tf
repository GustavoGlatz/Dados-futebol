terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "sa-east-1"
}

# Data sources
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_ssm_parameter" "api_key" {
  name            = "/projeto-futebol/api-key"
  with_decryption = true # para ler SecureString
}

# BUCKET S3
resource "aws_s3_bucket" "datalake_bucket" {
  bucket = "datalake-football-project-glatz"
  
  # Permite destruir bucket com arquivos
  force_destroy = true 

  tags = {
    Name        = "Projeto futebol"
    Environment = "Dev"
    Project     = "Treinamento Engenharia de Dados"
  }
}

# REGRAS DE LIMPEZA
resource "aws_s3_bucket_lifecycle_configuration" "limpeza_diaria" {
  bucket = aws_s3_bucket.datalake_bucket.id

  rule {
    id     = "limpar-camada-raw"
    status = "Enabled"

    filter {
      prefix = "raw/"
    }

    expiration {
      days = 1
    }
  }

  rule {
    id     = "limpar-camada-bronze"
    status = "Enabled"

    filter {
      prefix = "bronze/"
    }

    expiration {
      days = 1
    }
  }

  # REGRA 2: Limpa a pasta SILVER
  rule {
    id     = "limpar-camada-silver"
    status = "Enabled"

    filter {
      prefix = "silver/"
    }

    expiration {
      days = 1
    }
  }

  # REGRA 3: Limpa a pasta GOLD
  rule {
    id     = "limpar-camada-gold"
    status = "Enabled"

    filter {
      prefix = "gold/"
    }

    expiration {
      days = 1
    }
  }
}

# ECR REPOSITORY
resource "aws_ecr_repository" "repo" {
  name                 = "projeto-futebol" # Nome do repo
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
  
  force_delete = true 
}

# IAM ROLE
resource "aws_iam_role" "lambda_role" {
  name = "football_projeto_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" } 
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "s3_write_policy" {
  name = "lambda_s3_write"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = ["s3:PutObject"]
      Effect = "Allow"
      Resource = "${aws_s3_bucket.datalake_bucket.arn}/*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach_s3" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.s3_write_policy.arn
}

# FUNÇÃO LAMBDA 
resource "aws_lambda_function" "projeto_function" {
  function_name = "football_projeto_daily"
  role          = aws_iam_role.lambda_role.arn
  package_type  = "Image"
  
  image_uri     = "${aws_ecr_repository.repo.repository_url}:latest"
  
  timeout       = 60
  memory_size   = 512 

  environment {
    variables = {
      API_FOOTBALL_DATA_KEY = data.aws_ssm_parameter.api_key.value
      AWS_S3_BUCKET_NAME    = aws_s3_bucket.datalake_bucket.bucket
    }
  }

  # impede que o Terraform reverta a imagem quando o GitHub Actions atualizar o Lambda
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# EVENTBRIDGE PARA O LAMBDA
resource "aws_cloudwatch_event_rule" "daily_schedule" {
  name                = "projeto-futebol-daily"
  description         = "Dispara o ETL todo dia as 08:00 UTC e as 21:00 UTC"
  schedule_expression = "cron(0 8,21 * * ? *)"
}

resource "aws_cloudwatch_event_target" "trigger_lambda" {
  rule      = aws_cloudwatch_event_rule.daily_schedule.name
  target_id = "lambda"
  arn       = aws_lambda_function.projeto_function.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.projeto_function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_schedule.arn
}

# IAM Role para o AWS Glue
resource "aws_iam_role" "glue_role" {
  name = "football_glue_job_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "glue.amazonaws.com" }
    }]
  })
}

# Anexa a permissão gerenciada pelo AWS Glue
resource "aws_iam_role_policy_attachment" "glue_service" {
  role       = aws_iam_role.glue_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole"
}

# Política Específica para o Bucket S3
resource "aws_iam_policy" "glue_s3_policy" {
  name = "glue_s3_access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ]
        Resource = [
          "${aws_s3_bucket.datalake_bucket.arn}",
          "${aws_s3_bucket.datalake_bucket.arn}/*"
        ]
      }
    ]
  })
}

# Anexa a política ao Role do Glue
resource "aws_iam_role_policy_attachment" "attach_glue_s3" {
  role       = aws_iam_role.glue_role.name
  policy_arn = aws_iam_policy.glue_s3_policy.arn
}

# Job do AWS Glue
resource "aws_glue_job" "football_etl" {
  name     = "football_etl_job"
  role_arn = aws_iam_role.glue_role.arn
  
  # 4.0 = Spark 3.3 / Python 3.10
  glue_version = "4.0"
  
  # Tipo de Worker (G.1X é o mais barato)
  worker_type       = "G.1X"
  number_of_workers = 2 # Mínimo permitido
  
  command {
    script_location = "s3://${aws_s3_bucket.datalake_bucket.bucket}/scripts/etl_script.py"
    python_version  = "3"
  }

  # Passando o nome do bucket como argumento para o script Python
  default_arguments = {
    "--BUCKET_NAME" = aws_s3_bucket.datalake_bucket.bucket
  }
}

# 4. Trigger do Glue
resource "aws_glue_trigger" "daily_etl_trigger" {
  name     = "football_daily_trigger"
  type     = "SCHEDULED"
  schedule = "cron(15 8,21 * * ? *)" 

  actions {
    job_name = aws_glue_job.football_etl.name
  }
}