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

import json
import logging
import os
import time
from decimal import Decimal
import onnxruntime as ort
from tokenizers import Tokenizer
import numpy as np

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Global variables for caching
model = None
tokenizer = None
MODEL_PATH = os.environ.get('MODEL_PATH', '/tmp/model_assets')
MODEL_BUCKET = os.environ.get('MODEL_BUCKET')
try:
    s3_client = boto3.client('s3')
    dynamodb = boto3.resource('dynamodb')
    AWS_AVAILABLE = True
except Exception:
    AWS_AVAILABLE = False

def get_secret():
    if not AWS_AVAILABLE: return None
    
    secret_name = os.environ.get('SECRET_ARN')
    region_name = os.environ.get('AWS_REGION', 'us-west-2')

    if not secret_name:
        logger.warning("SECRET_ARN not set. Skipping.")
        return None

    try:
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name=region_name)
        response = client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in response:
            logger.info("Successfully retrieved runtime secret")
            return json.loads(response['SecretString'])
    except Exception as e:
        logger.error(f"Failed to retrieve secret: {e}")
        return None

# Runtime Secret Retrieval (Credential Elimination)
API_SECRETS = get_secret()


def softmax(x):
    """Compute softmax values for each sets of scores in x."""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum(axis=0)

def download_model_from_s3():
    """Download model assets from S3 to /tmp"""
    if not os.path.exists(MODEL_PATH):
        os.makedirs(MODEL_PATH)
    
    logger.info(f"Downloading model from s3://{MODEL_BUCKET}/model_assets ...")
    
    try:
        if not MODEL_BUCKET:
            logger.warning("MODEL_BUCKET not set. Assuming local model.")
            return

        objects = s3_client.list_objects_v2(Bucket=MODEL_BUCKET, Prefix="model_assets/")
        if 'Contents' not in objects:
            logger.error("No model assets found in S3")
            return # Don't raise, might be local test or preloaded

        for obj in objects['Contents']:
            key = obj['Key']
            rel_path = os.path.relpath(key, "model_assets")
            if rel_path == ".": continue
            local_file = os.path.join(MODEL_PATH, rel_path)
            local_dir = os.path.dirname(local_file)
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
            
            logger.info(f"Downloading {key} to {local_file}")
            s3_client.download_file(MODEL_BUCKET, key, local_file)
    except Exception as e:
        logger.error(f"Failed to download model: {e}")
        # raise e # Don't crash if optional? But for Lambda it's critical.
        raise e

def load_model():
    global model, tokenizer
    if model is None or tokenizer is None:
        try:
            logger.info("Loading ONNX model and tokenizer...")
            
            if not os.path.exists(os.path.join(MODEL_PATH, "model.onnx")):
                download_model_from_s3()
            
            # Load Tokenizer from tokenizer.json
            metrics_path = os.path.join(MODEL_PATH, "tokenizer.json")
            if not os.path.exists(metrics_path):
                 # Fallback/Error? download should have fetched it. 
                 raise Exception("tokenizer.json not found")

            tokenizer = Tokenizer.from_file(metrics_path)
            # Enable truncation and padding
            tokenizer.enable_truncation(max_length=512)
            tokenizer.enable_padding(length=512)

            # Load ONNX Model
            model_file = os.path.join(MODEL_PATH, "model.onnx")
            model = ort.InferenceSession(model_file)
            
            logger.info("Model loaded successfully")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            raise e

def analyze_sentiment(text):
    """Analyze sentiment using ONNX Runtime and Tokenizers"""
    global model, tokenizer
    
    if model is None or tokenizer is None:
        load_model()
    
    # Tokenize
    encoded = tokenizer.encode(text)
    
    # Prepare inputs for ONNX (DistilBERT expects input_ids and attention_mask)
    # The names must match the ONNX model input names. Usually 'input_ids', 'attention_mask'.
    # We can check model.get_inputs() but standard DistilBERT is standard.
    
    input_ids = np.array([encoded.ids], dtype=np.int64)
    attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
    
    onnx_inputs = {
        'input_ids': input_ids,
        'attention_mask': attention_mask
    }
    
    # Inference
    outputs = model.run(None, onnx_inputs)
    logits = outputs[0][0]
    
    # Post-process
    probabilities = softmax(logits)
    sentiment_idx = np.argmax(probabilities)
    confidence = float(probabilities[sentiment_idx])
    
    labels = ["NEGATIVE", "POSITIVE"]
    sentiment = labels[sentiment_idx]
    
    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "text_preview": text[:100]
    }


def save_to_dynamodb(user_id: str, text: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save analysis result to DynamoDB.
    Returns status dict with success/error details.
    """
    if not AWS_AVAILABLE:
        # Local testing mock
        return {"success": True, "message": "Local mode (skipped DB)"}
    
    try:
        table_name = os.environ.get('DYNAMODB_TABLE')
        if not table_name:
             return {"success": False, "error": "DYNAMODB_TABLE env var missing"}

        table = dynamodb.Table(table_name)
        timestamp = int(datetime.now().timestamp())
        
        item = {
            'PK': f'USER#{user_id}',
            'SK': f'ANALYSIS#{timestamp}',
            'text': text,
            'sentiment': result['sentiment'],
            'confidence': Decimal(str(result['confidence'])),
            'timestamp': timestamp,
            'created_at': datetime.now().isoformat()
        }
        
        table.put_item(Item=item)
        logger.info(f"Saved result to DynamoDB for user {user_id}")
        return {"success": True}
        
    except Exception as e:
        logger.error(f"Error saving to DynamoDB: {str(e)}")
        return {"success": False, "error": str(e)}


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Lambda function handler for sentiment analysis.
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
        
        # Save to DynamoDB
        db_status = save_to_dynamodb(user_id, text, result)
        
        # Return successful response
        response_body = {
            'user_id': user_id,
            'sentiment': result['sentiment'],
            'confidence': result['confidence'],
            'timestamp': int(datetime.now().timestamp()),
            'text_preview': result['text_preview'],
            'db_save_status': db_status # Debug field
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
    AWS_AVAILABLE = False
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
