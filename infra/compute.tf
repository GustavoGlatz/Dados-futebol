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