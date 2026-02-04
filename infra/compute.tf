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

  lifecycle {
    ignore_changes = [image_uri]
  }
}

resource "aws_glue_job" "football_etl" {
  name     = "football_etl_job"
  role_arn = aws_iam_role.glue_role.arn
  
  glue_version = "4.0"
  
  worker_type       = "G.1X"
  number_of_workers = 2 
  
  command {
    script_location = "s3://${aws_s3_bucket.datalake_bucket.bucket}/scripts/etl_script.py"
    python_version  = "3"
  }

  default_arguments = {
    "--BUCKET_NAME" = aws_s3_bucket.datalake_bucket.bucket
    "--datalake-formats" = "delta"
    "--conf"             = "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension --conf spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog"
  }
}

# Lambda para disparar Glue Job via EventBridge
resource "aws_lambda_function" "trigger_glue_job" {
  function_name = "trigger_football_etl"
  role          = aws_iam_role.lambda_trigger_glue_role.arn
  handler       = "index.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30

  filename         = data.archive_file.lambda_trigger_glue.output_path
  source_code_hash = data.archive_file.lambda_trigger_glue.output_base64sha256

  environment {
    variables = {
      GLUE_JOB_NAME = aws_glue_job.football_etl.name
    }
  }
}

data "archive_file" "lambda_trigger_glue" {
  type        = "zip"
  output_path = "${path.module}/lambda_trigger_glue.zip"

  source {
    content  = <<-EOF
      import boto3
      import os
      import json
      
      glue_client = boto3.client('glue')
      
      def lambda_handler(event, context):
          job_name = os.environ['GLUE_JOB_NAME']
          
          try:
              response = glue_client.start_job_run(JobName=job_name)
              print(f"Glue Job iniciado: {response['JobRunId']}")
              
              return {
                  'statusCode': 200,
                  'body': json.dumps({
                      'message': 'Glue Job iniciado com sucesso',
                      'jobRunId': response['JobRunId']
                  })
              }
          except Exception as e:
              print(f"Erro ao iniciar Glue Job: {str(e)}")
              raise
    EOF
    filename = "index.py"
  }
}