"""
Batch Processing Lambda Function
Processes CSV files containing multiple text samples for sentiment analysis
"""

import json
import os
import boto3
import logging
import csv
from io import StringIO
from datetime import datetime
from typing import Dict, Any, List
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# AWS clients
try:
    s3_client = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    sns_client = boto3.client('sns')
    AWS_AVAILABLE = True
except Exception as e:
    logger.warning(f"AWS services not available: {e}")
    AWS_AVAILABLE = False

# Environment variables
MODEL_BUCKET = os.environ.get('MODEL_BUCKET', 'local-test-bucket')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'local-test-table')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')

# Global variables for model
model = None
tokenizer = None


def load_model():
    """Load the sentiment analysis model"""
    global model, tokenizer
    
    if model is not None and tokenizer is not None:
        return
    
    logger.info("Loading sentiment analysis model...")
    
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        
        model_name = "distilbert-base-uncased-finetuned-sst-2-english"
        
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        model.eval()
        
        logger.info("Model loaded successfully")
        
    except Exception as e:
        logger.error(f"Error loading model: {str(e)}")
        raise


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """Analyze sentiment of a single text"""
    global model, tokenizer
    
    if model is None or tokenizer is None:
        load_model()
    
    try:
        import torch
        
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        
        with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        confidence, predicted_class = torch.max(predictions, dim=1)
        
        sentiment_map = {0: "NEGATIVE", 1: "POSITIVE"}
        sentiment = sentiment_map[predicted_class.item()]
        confidence_score = float(confidence.item())
        
        return {
            "sentiment": sentiment,
            "confidence": confidence_score
        }
        
    except Exception as e:
        logger.error(f"Error during inference: {str(e)}")
        return {
            "sentiment": "ERROR",
            "confidence": 0.0,
            "error": str(e)
        }


def process_csv_file(bucket: str, key: str) -> List[Dict[str, Any]]:
    """
    Download and process CSV file from S3
    
    Expected CSV format:
    text,user_id (optional)
    "I love this!",user123
    "This is bad",user456
    """
    if not AWS_AVAILABLE:
        logger.info("AWS not available - using sample data for local testing")
        return [
            {"text": "I love this!", "row": 0},
            {"text": "This is terrible", "row": 1},
            {"text": "It's okay", "row": 2}
        ]
    
    try:
        # Download CSV from S3
        response = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = response['Body'].read().decode('utf-8')
        
        # Parse CSV
        csv_reader = csv.DictReader(StringIO(csv_content))
        
        rows = []
        for i, row in enumerate(csv_reader):
            if 'text' in row:
                rows.append({
                    'text': row['text'],
                    'user_id': row.get('user_id', 'anonymous'),
                    'row': i
                })
        
        logger.info(f"Loaded {len(rows)} rows from CSV")
        return rows
        
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}")
        raise


def save_batch_results(batch_id: str, results: List[Dict[str, Any]]) -> None:
    """Save batch processing results to DynamoDB"""
    if not AWS_AVAILABLE:
        logger.info("AWS not available - skipping DynamoDB save")
        return
    
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        timestamp = int(datetime.now().timestamp())
        
        # Save each result
        for result in results:
            item = {
                'PK': f'BATCH#{batch_id}',
                'SK': f'ROW#{str(result["row"]).zfill(6)}',
                'text': result['text'],
                'sentiment': result['sentiment'],
                'confidence': Decimal(str(result['confidence'])),
                'user_id': result.get('user_id', 'anonymous'),
                'timestamp': timestamp,
                'status': result.get('status', 'success')
            }
            
            table.put_item(Item=item)
        
        # Save batch summary
        success_count = sum(1 for r in results if r.get('status') == 'success')
        failed_count = len(results) - success_count
        
        summary = {
            'PK': f'BATCH#{batch_id}',
            'SK': 'SUMMARY',
            'total_rows': len(results),
            'success_count': success_count,
            'failed_count': failed_count,
            'status': 'COMPLETED',
            'timestamp': timestamp,
            'completed_at': datetime.now().isoformat()
        }
        
        table.put_item(Item=summary)
        logger.info(f"Saved batch results: {success_count} success, {failed_count} failed")
        
    except Exception as e:
        logger.error(f"Error saving batch results: {str(e)}")
        raise


def send_completion_notification(batch_id: str, success_count: int, failed_count: int) -> None:
    """Send SNS notification when batch is complete"""
    if not AWS_AVAILABLE or not SNS_TOPIC_ARN:
        logger.info("SNS not configured - skipping notification")
        return
    
    try:
        message = f"""
Batch Processing Complete

Batch ID: {batch_id}
Total Rows: {success_count + failed_count}
Successful: {success_count}
Failed: {failed_count}
Completed At: {datetime.now().isoformat()}
        """
        
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f'Batch {batch_id} Processing Complete',
            Message=message
        )
        
        logger.info(f"Sent completion notification for batch {batch_id}")
        
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Lambda handler for batch processing
    
    Expected event format:
    {
        "bucket": "my-bucket",
        "key": "uploads/batch123.csv",
        "batch_id": "batch-123"
    }
    
    OR from API Gateway:
    {
        "body": "{\"bucket\": \"...\", \"key\": \"...\", \"batch_id\": \"...\"}"
    }
    """
    logger.info(f"Received batch processing request: {json.dumps(event, default=str)}")
    
    try:
        # Parse request
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        bucket = body.get('bucket', MODEL_BUCKET)
        key = body.get('key', '')
        batch_id = body.get('batch_id', f"batch-{int(datetime.now().timestamp())}")
        
        if not key:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'CSV key is required'})
            }
        
        # Process CSV file
        logger.info(f"Processing batch {batch_id} from s3://{bucket}/{key}")
        rows = process_csv_file(bucket, key)
        
        if not rows:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No valid rows found in CSV'})
            }
        
        # Analyze sentiment for each row
        results = []
        for row in rows:
            try:
                sentiment_result = analyze_sentiment(row['text'])
                results.append({
                    'row': row['row'],
                    'text': row['text'],
                    'user_id': row.get('user_id', 'anonymous'),
                    'sentiment': sentiment_result['sentiment'],
                    'confidence': sentiment_result['confidence'],
                    'status': 'success'
                })
            except Exception as e:
                logger.error(f"Error processing row {row['row']}: {str(e)}")
                results.append({
                    'row': row['row'],
                    'text': row['text'],
                    'sentiment': 'ERROR',
                    'confidence': 0.0,
                    'status': 'failed',
                    'error': str(e)
                })
        
        # Save results to DynamoDB
        save_batch_results(batch_id, results)
        
        # Send notification
        success_count = sum(1 for r in results if r['status'] == 'success')
        failed_count = len(results) - success_count
        send_completion_notification(batch_id, success_count, failed_count)
        
        # Return response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'batch_id': batch_id,
                'total_rows': len(results),
                'success_count': success_count,
                'failed_count': failed_count,
                'status': 'COMPLETED',
                'message': f'Processed {len(results)} rows successfully'
            })
        }
        
    except Exception as e:
        logger.error(f"Batch processing error: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Batch processing failed',
                'message': str(e)
            })
        }


# For local testing
if __name__ == "__main__":
    print("=== Testing Batch Processing Lambda ===\n")
    
    # Test with sample data
    test_event = {
        "bucket": "test-bucket",
        "key": "test.csv",
        "batch_id": "test-batch-001"
    }
    
    response = lambda_handler(test_event)
    
    print(f"Status Code: {response['statusCode']}")
    print(f"Response: {json.dumps(json.loads(response['body']), indent=2)}")
