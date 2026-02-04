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

resource "aws_cloudwatch_event_rule" "s3_upload_trigger" {
  name        = "trigger-glue-on-s3-upload"
  description = "Dispara o ETL Glue quando um arquivo JSON cai na RAW"

  event_pattern = jsonencode({
    "source": ["aws.s3"],
    "detail-type": ["Object Created"],
    "detail": {
      "bucket": {
        "name": [aws_s3_bucket.datalake_bucket.bucket]
      },
      "object": {
        "key": [{ "prefix": "raw/" }] 
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "target_glue_s3" {
  rule      = aws_cloudwatch_event_rule.s3_upload_trigger.name
  target_id = "TriggerGlueLambda"
  arn       = aws_lambda_function.trigger_glue_job.arn
}

resource "aws_lambda_permission" "allow_eventbridge_trigger_glue" {
  statement_id  = "AllowExecutionFromEventBridgeS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trigger_glue_job.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.s3_upload_trigger.arn
}