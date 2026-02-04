resource "aws_s3_bucket" "datalake_bucket" {
  bucket = "datalake-football-project-glatz"
  
  force_destroy = true 

  tags = {
    Name        = "Projeto futebol"
    Environment = "Dev"
    Project     = "Treinamento Engenharia de Dados"
  }
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket      = aws_s3_bucket.datalake_bucket.id
  eventbridge = true
}

resource "aws_ecr_repository" "repo" {
  name                 = "projeto-futebol"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
  
  force_delete = true 
}

resource "aws_ecr_lifecycle_policy" "limpeza_imagens" {
  repository = aws_ecr_repository.repo.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Remove imagens antigas sem tag"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}