"""
History Retrieval Lambda Function
Retrieves user's sentiment analysis history from DynamoDB
"""

import json
import os
import boto3
import logging
from typing import Dict, Any, List
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# AWS clients
try:
    dynamodb = boto3.resource('dynamodb')
    AWS_AVAILABLE = True
except Exception as e:
    logger.warning(f"AWS services not available: {e}")
    AWS_AVAILABLE = False

# Environment variables
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'local-test-table')


class DecimalEncoder(json.JSONEncoder):
    """Helper class to convert Decimal to float for JSON serialization"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def get_user_history(user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Retrieve user's analysis history from DynamoDB
    
    Args:
        user_id: User identifier
        limit: Maximum number of results to return
        
    Returns:
        List of analysis results
    """
    if not AWS_AVAILABLE:
        logger.info("AWS not available - returning sample data for local testing")
        return [
            {
                "text": "I love this product!",
                "sentiment": "POSITIVE",
                "confidence": 0.9987,
                "timestamp": 1699900000,
                "created_at": "2024-11-13T10:00:00"
            },
            {
                "text": "This is terrible",
                "sentiment": "NEGATIVE",
                "confidence": 0.9876,
                "timestamp": 1699900060,
                "created_at": "2024-11-13T10:01:00"
            },
            {
                "text": "It's okay",
                "sentiment": "POSITIVE",
                "confidence": 0.5123,
                "timestamp": 1699900120,
                "created_at": "2024-11-13T10:02:00"
            }
        ]
    
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        
        # Query user's analysis history
        response = table.query(
            KeyConditionExpression=Key('PK').eq(f'USER#{user_id}') & Key('SK').begins_with('ANALYSIS#'),
            Limit=limit,
            ScanIndexForward=False  # Most recent first
        )
        
        items = response.get('Items', [])
        
        # Format results
        results = []
        for item in items:
            results.append({
                'text': item.get('text', ''),
                'sentiment': item.get('sentiment', ''),
                'confidence': float(item.get('confidence', 0.0)),
                'timestamp': item.get('timestamp', 0),
                'created_at': item.get('created_at', '')
            })
        
        logger.info(f"Retrieved {len(results)} history items for user {user_id}")
        return results
        
    except Exception as e:
        logger.error(f"Error retrieving history: {str(e)}")
        raise


def get_batch_results(batch_id: str) -> Dict[str, Any]:
    """
    Retrieve batch processing results
    
    Args:
        batch_id: Batch identifier
        
    Returns:
        Dictionary with batch summary and results
    """
    if not AWS_AVAILABLE:
        logger.info("AWS not available - returning sample data for local testing")
        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "total_rows": 100,
            "success_count": 98,
            "failed_count": 2,
            "results": [
                {"row": 0, "text": "Sample 1", "sentiment": "POSITIVE", "confidence": 0.95},
                {"row": 1, "text": "Sample 2", "sentiment": "NEGATIVE", "confidence": 0.87}
            ]
        }
    
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        
        # Get batch summary
        summary_response = table.get_item(
            Key={
                'PK': f'BATCH#{batch_id}',
                'SK': 'SUMMARY'
            }
        )
        
        summary = summary_response.get('Item', {})
        
        if not summary:
            return {
                'error': 'Batch not found',
                'batch_id': batch_id
            }
        
        # Get batch results
        results_response = table.query(
            KeyConditionExpression=Key('PK').eq(f'BATCH#{batch_id}') & Key('SK').begins_with('ROW#'),
            Limit=1000  # Adjust based on expected batch size
        )
        
        results = []
        for item in results_response.get('Items', []):
            results.append({
                'row': int(item['SK'].split('#')[1]),
                'text': item.get('text', ''),
                'sentiment': item.get('sentiment', ''),
                'confidence': float(item.get('confidence', 0.0)),
                'status': item.get('status', 'unknown')
            })
        
        # Sort by row number
        results.sort(key=lambda x: x['row'])
        
        return {
            'batch_id': batch_id,
            'status': summary.get('status', 'UNKNOWN'),
            'total_rows': int(summary.get('total_rows', 0)),
            'success_count': int(summary.get('success_count', 0)),
            'failed_count': int(summary.get('failed_count', 0)),
            'completed_at': summary.get('completed_at', ''),
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Error retrieving batch results: {str(e)}")
        raise


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """
    Lambda handler for history retrieval
    
    Expected event format (API Gateway):
    {
        "queryStringParameters": {
            "user_id": "user123",
            "limit": "50"
        }
    }
    
    OR for batch results:
    {
        "queryStringParameters": {
            "batch_id": "batch-123"
        }
    }
    """
    logger.info(f"Received history request: {json.dumps(event, default=str)}")
    
    try:
        # Parse query parameters
        params = event.get('queryStringParameters', {}) or {}
        
        user_id = params.get('user_id')
        batch_id = params.get('batch_id')
        limit = int(params.get('limit', 50))
        
        # Validate limit
        if limit > 1000:
            limit = 1000
        if limit < 1:
            limit = 10
        
        # Determine what to retrieve
        if batch_id:
            # Retrieve batch results
            results = get_batch_results(batch_id)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(results, cls=DecimalEncoder)
            }
            
        elif user_id:
            # Retrieve user history
            history = get_user_history(user_id, limit)
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'user_id': user_id,
                    'count': len(history),
                    'history': history
                }, cls=DecimalEncoder)
            }
            
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Either user_id or batch_id parameter is required'
                })
            }
        
    except Exception as e:
        logger.error(f"History retrieval error: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'Failed to retrieve history',
                'message': str(e)
            })
        }


# For local testing
if __name__ == "__main__":
    print("=== Testing History Lambda ===\n")
    
    # Test 1: Get user history
    print("Test 1: Get user history")
    test_event_1 = {
        "queryStringParameters": {
            "user_id": "test-user-123",
            "limit": "10"
        }
    }
    
    response_1 = lambda_handler(test_event_1)
    print(f"Status: {response_1['statusCode']}")
    print(f"Response: {json.dumps(json.loads(response_1['body']), indent=2)}")
    print("-" * 60)
    
    # Test 2: Get batch results
    print("\nTest 2: Get batch results")
    test_event_2 = {
        "queryStringParameters": {
            "batch_id": "batch-001"
        }
    }
    
    response_2 = lambda_handler(test_event_2)
    print(f"Status: {response_2['statusCode']}")
    print(f"Response: {json.dumps(json.loads(response_2['body']), indent=2)}")
    print("-" * 60)
    
    # Test 3: Missing parameters
    print("\nTest 3: Missing parameters (should fail)")
    test_event_3 = {
        "queryStringParameters": {}
    }
    
    response_3 = lambda_handler(test_event_3)
    print(f"Status: {response_3['statusCode']}")
    print(f"Response: {json.dumps(json.loads(response_3['body']), indent=2)}")
