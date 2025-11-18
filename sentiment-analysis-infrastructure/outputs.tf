output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = "${aws_api_gateway_stage.main.invoke_url}"
}

output "cloudfront_url" {
  description = "CloudFront distribution URL"
  value       = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "frontend_bucket" {
  description = "S3 bucket name for frontend"
  value       = aws_s3_bucket.frontend.id
}

output "data_bucket" {
  description = "S3 bucket name for data storage"
  value       = aws_s3_bucket.data.id
}

output "dynamodb_table" {
  description = "DynamoDB table name"
  value       = aws_dynamodb_table.sentiment_analytics.name
}

output "lambda_functions" {
  description = "Lambda function names"
  value = {
    sentiment_analyzer = aws_lambda_function.sentiment_analyzer.function_name
    batch_processor    = aws_lambda_function.batch_processor.function_name
    history_handler    = aws_lambda_function.history_handler.function_name
  }
}

output "api_gateway_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.main.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.main.id
}

output "sns_topic_arn" {
  description = "SNS topic ARN for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "deployment_instructions" {
  description = "Next steps after Terraform apply"
  value = <<-EOT
    ✅ Infrastructure deployed successfully!
    
    Next steps:
    
    1. Package and upload Lambda functions:
       
       cd ../backend/sentiment_analyzer
       pip install -r requirements.txt -t package/ --platform manylinux2014_x86_64 --only-binary=:all:
       cp lambda_function.py package/
       cd package && zip -r ../sentiment_analyzer.zip . && cd ..
       
       aws lambda update-function-code \
         --function-name ${aws_lambda_function.sentiment_analyzer.function_name} \
         --zip-file fileb://sentiment_analyzer.zip
    
    2. Upload frontend to S3:
       
       cd ../frontend
       aws s3 cp index.html s3://${aws_s3_bucket.frontend.id}/
    
    3. Update frontend with API endpoint:
       
       Edit index.html and replace API_ENDPOINT with:
       ${aws_api_gateway_stage.main.invoke_url}
    
    4. Invalidate CloudFront cache:
       
       aws cloudfront create-invalidation \
         --distribution-id ${aws_cloudfront_distribution.main.id} \
         --paths "/*"
    
    5. Confirm SNS email subscription (check your email)
    
    6. Access your app at:
       https://${aws_cloudfront_distribution.main.domain_name}
  EOT
}
