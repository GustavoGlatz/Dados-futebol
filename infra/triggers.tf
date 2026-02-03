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

resource "aws_glue_trigger" "daily_etl_trigger" {
  name     = "football_daily_trigger"
  type     = "SCHEDULED"
  schedule = "cron(15 8 * * ? *)" 

  actions {
    job_name = aws_glue_job.football_etl.name
  }
}