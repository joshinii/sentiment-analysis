"""
Sentiment Analysis Lambda Function
Analyzes text sentiment using pre-trained DistilBERT model from HuggingFace
"""

import json
import os
import boto3
import logging
from datetime import datetime
from typing import Dict, Any
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# AWS clients (will be None in local testing)
try:
    s3_client = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    AWS_AVAILABLE = True
except Exception as e:
    logger.warning(f"AWS services not available: {e}")
    AWS_AVAILABLE = False

# Environment variables
MODEL_BUCKET = os.environ.get('MODEL_BUCKET', 'local-test-bucket')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'local-test-table')
MODEL_KEY = os.environ.get('MODEL_KEY', 'models/distilbert-sentiment/')

# Global variables for model (loaded once per container)
model = None
tokenizer = None


def load_model():
    """
    Load the pre-trained sentiment analysis model.
    In production: Downloads from S3
    In local testing: Uses HuggingFace cache
    """
    global model, tokenizer
    
    if model is not None and tokenizer is not None:
        logger.info("Model already loaded, skipping...")
        return
    
    logger.info("Loading sentiment analysis model...")
    
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        
        # Use a lightweight model that works in Lambda
        model_name = "distilbert-base-uncased-finetuned-sst-2-english"
        
        logger.info(f"Loading model: {model_name}")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        
        # Set to evaluation mode
        model.eval()
        
        logger.info("Model loaded successfully")
        
    except Exception as e:
        logger.error(f"Error loading model: {str(e)}")
        raise


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    Analyze sentiment of input text.
    
    Args:
        text: Input text to analyze
        
    Returns:
        Dictionary containing sentiment label and confidence score
    """
    global model, tokenizer
    
    # Ensure model is loaded
    if model is None or tokenizer is None:
        load_model()
    
    try:
        import torch
        
        # Tokenize input
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        
        # Run inference
        with torch.no_grad():
            outputs = model(**inputs)
            predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        # Get predicted class and confidence
        confidence, predicted_class = torch.max(predictions, dim=1)
        
        # Map class to label (0 = NEGATIVE, 1 = POSITIVE)
        sentiment_map = {0: "NEGATIVE", 1: "POSITIVE"}
        sentiment = sentiment_map[predicted_class.item()]
        confidence_score = float(confidence.item())
        
        logger.info(f"Sentiment: {sentiment}, Confidence: {confidence_score:.4f}")
        
        return {
            "sentiment": sentiment,
            "confidence": confidence_score,
            "text_preview": text[:100] if len(text) > 100 else text
        }
        
    except Exception as e:
        logger.error(f"Error during inference: {str(e)}")
        raise


def save_to_dynamodb(user_id: str, text: str, result: Dict[str, Any]) -> None:
    """
    Save analysis result to DynamoDB.
    Skipped in local testing if AWS is not available.
    
    Args:
        user_id: User identifier
        text: Original input text
        result: Analysis result dictionary
    """
    if not AWS_AVAILABLE:
        logger.info("AWS not available - skipping DynamoDB save (local testing)")
        return
    
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        timestamp = int(datetime.now().timestamp())
        
        item = {
            'PK': f'USER#{user_id}',
            'SK': f'ANALYSIS#{timestamp}',
            'text': text,
            'sentiment': result['sentiment'],
            'confidence': Decimal(str(result['confidence'])),  # DynamoDB requires Decimal
            'timestamp': timestamp,
            'created_at': datetime.now().isoformat()
        }
        
        table.put_item(Item=item)
        logger.info(f"Saved result to DynamoDB for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {str(e)}")
        # Don't raise - we still want to return the result to the user


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Lambda function handler for sentiment analysis.
    
    Expected event format:
    {
        "text": "I love this product!",
        "user_id": "user123"  # Optional
    }
    
    Returns:
        API Gateway response with sentiment analysis result
    """
    logger.info(f"Received event: {json.dumps(event, default=str)}")
    
    try:
        # Parse request body (from API Gateway)
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
        
        # Extract text from request
        text = body.get('text', '')
        user_id = body.get('user_id', 'anonymous')
        
        # Validate input
        if not text or len(text.strip()) == 0:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Text field is required and cannot be empty'
                })
            }
        
        if len(text) > 5000:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Text exceeds maximum length of 5000 characters'
                })
            }
        
        # Perform sentiment analysis
        result = analyze_sentiment(text)
        
        # Save to DynamoDB (async, don't wait)
        try:
            save_to_dynamodb(user_id, text, result)
        except Exception as e:
            logger.warning(f"Failed to save to DynamoDB: {str(e)}")
        
        # Return successful response
        response_body = {
            'sentiment': result['sentiment'],
            'confidence': result['confidence'],
            'timestamp': int(datetime.now().timestamp()),
            'text_preview': result['text_preview']
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(response_body)
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Internal server error',
                'message': str(e)
            })
        }


# For local testing
if __name__ == "__main__":
    print("=== Testing Sentiment Analysis Lambda ===\n")
    
    # Test cases
    test_cases = [
        {
            "text": "I absolutely love this product! It's amazing!",
            "user_id": "test-user-1"
        },
        {
            "text": "This is terrible. Worst purchase ever.",
            "user_id": "test-user-2"
        },
        {
            "text": "The product is okay, nothing special.",
            "user_id": "test-user-3"
        },
        {
            "text": "Outstanding quality and excellent customer service!",
            "user_id": "test-user-4"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test Case {i}:")
        print(f"Input: {test_case['text']}")
        
        response = lambda_handler(test_case)
        
        if response['statusCode'] == 200:
            result = json.loads(response['body'])
            print(f"Sentiment: {result['sentiment']}")
            print(f"Confidence: {result['confidence']:.4f}")
        else:
            print(f"Error: {response['body']}")
        
        print("-" * 60)
