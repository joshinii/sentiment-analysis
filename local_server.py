"""
Local Flask Server for Sentiment Analysis Frontend Testing
Includes all 3 endpoints: /analyze, /batch, /history
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sys
import os
import json
from datetime import datetime
import time

# Add Lambda function to path - For root directory location
lambda_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'sentiment_analyzer')
sys.path.insert(0, lambda_path)

# Add batch processor to path
batch_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'batch_processor')
sys.path.insert(0, batch_path)

# Add history handler to path
history_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'history')
sys.path.insert(0, history_path)

try:
    import lambda_function
    print("✅ Sentiment analyzer loaded")
except ImportError as e:
    print(f"❌ Error importing sentiment analyzer: {e}")
    sys.exit(1)

try:
    import batch_handler
    print("✅ Batch processor loaded")
except ImportError as e:
    print(f"⚠️  Batch processor not loaded: {e}")
    batch_handler = None

try:
    import history_handler
    print("✅ History handler loaded")
except ImportError as e:
    print(f"⚠️  History handler not loaded: {e}")
    history_handler = None

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# In-memory storage for local testing (simulates DynamoDB)
local_history = []

@app.route('/analyze', methods=['POST', 'OPTIONS'])
def analyze():
    """Sentiment analysis endpoint"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        if not data or 'text' not in data:
            return jsonify({'error': 'Missing text field'}), 400
        
        # Call Lambda function
        result = lambda_function.lambda_handler(data, None)
        
        # Parse response
        if result['statusCode'] == 200:
            body = json.loads(result['body'])
            
            # Save to local history for testing
            history_item = {
                'user_id': body.get('user_id', 'anonymous'),
                'text': data['text'],
                'sentiment': body['sentiment'],
                'confidence': body['confidence'],
                'timestamp': int(time.time()),
                'created_at': datetime.now().isoformat()
            }
            local_history.append(history_item)
            
            # Keep only last 100 items
            if len(local_history) > 100:
                local_history.pop(0)
            
            return jsonify(body), 200
        else:
            body = json.loads(result['body'])
            return jsonify(body), result['statusCode']
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/batch', methods=['POST', 'OPTIONS'])
def batch():
    """Batch processing endpoint"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        if not data or 'texts' not in data:
            return jsonify({'error': 'Missing texts field'}), 400
        
        texts = data['texts']
        user_id = data.get('user_id', 'batch-user')
        
        results = []
        success_count = 0
        failed_count = 0
        
        for i, text in enumerate(texts):
            try:
                # Analyze each text
                analysis_data = {'text': text, 'user_id': f"{user_id}-{i}"}
                result = lambda_function.lambda_handler(analysis_data, None)
                
                if result['statusCode'] == 200:
                    body = json.loads(result['body'])
                    results.append({
                        'row': i,
                        'text': text,
                        'sentiment': body['sentiment'],
                        'confidence': body['confidence'],
                        'status': 'success'
                    })
                    success_count += 1
                    
                    # Save to history
                    local_history.append({
                        'user_id': f"{user_id}-{i}",
                        'text': text,
                        'sentiment': body['sentiment'],
                        'confidence': body['confidence'],
                        'timestamp': int(time.time()),
                        'created_at': datetime.now().isoformat()
                    })
                else:
                    results.append({
                        'row': i,
                        'text': text,
                        'status': 'failed',
                        'error': 'Processing failed'
                    })
                    failed_count += 1
                    
            except Exception as e:
                results.append({
                    'row': i,
                    'text': text,
                    'status': 'failed',
                    'error': str(e)
                })
                failed_count += 1
        
        response = {
            'batch_id': f"batch-{int(time.time())}",
            'total_rows': len(texts),
            'success_count': success_count,
            'failed_count': failed_count,
            'status': 'COMPLETED',
            'results': results[:10],  # Return first 10 for preview
            'message': f'Processed {success_count}/{len(texts)} texts successfully'
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/history', methods=['GET', 'OPTIONS'])
def history():
    """History retrieval endpoint"""
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        user_id = request.args.get('user_id')
        limit = int(request.args.get('limit', 10))
        
        if not user_id:
            return jsonify({'error': 'Missing user_id parameter'}), 400
        
        # Filter history by user_id
        user_history = [
            item for item in local_history 
            if item['user_id'] == user_id or item['user_id'].startswith(user_id)
        ]
        
        # Sort by timestamp (newest first)
        user_history.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Apply limit
        user_history = user_history[:limit]
        
        if not user_history:
            # Return sample data if no history found
            sample_data = {
                'user_id': user_id,
                'count': 0,
                'history': [],
                'message': 'No history found. Analyze some texts first!'
            }
            return jsonify(sample_data), 200
        
        response = {
            'user_id': user_id,
            'count': len(user_history),
            'history': user_history
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'message': 'Sentiment Analysis Local Server is running',
        'endpoints': {
            'analyze': 'POST /analyze',
            'batch': 'POST /batch',
            'history': 'GET /history?user_id=xxx',
            'health': 'GET /health'
        },
        'local_history_count': len(local_history)
    })


@app.route('/', methods=['GET'])
def home():
    """Home endpoint with instructions"""
    return f'''
    <html>
    <head><title>Sentiment Analysis API</title></head>
    <body style="font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px;">
        <h1>🎭 Sentiment Analysis Local Server</h1>
        <p>Your local API server is running successfully!</p>
        
        <h2>📊 Status:</h2>
        <ul>
            <li>✅ Server: Running</li>
            <li>✅ Sentiment Analyzer: Loaded</li>
            <li>✅ Batch Processor: Ready</li>
            <li>✅ History Handler: Ready</li>
            <li>📝 Local History: {len(local_history)} items stored</li>
        </ul>
        
        <h2>🔌 Endpoints:</h2>
        <ul>
            <li><strong>POST /analyze</strong> - Analyze single text</li>
            <li><strong>POST /batch</strong> - Process multiple texts</li>
            <li><strong>GET /history</strong> - Retrieve user history</li>
            <li><strong>GET /health</strong> - Health check</li>
        </ul>
        
        <h2>🧪 Test Commands:</h2>
        
        <h3>1. Analyze Text:</h3>
        <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px;">
curl -X POST http://localhost:5000/analyze \\
  -H "Content-Type: application/json" \\
  -d '{{"text":"I love this!","user_id":"test"}}'
        </pre>
        
        <h3>2. Batch Process:</h3>
        <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px;">
curl -X POST http://localhost:5000/batch \\
  -H "Content-Type: application/json" \\
  -d '{{"texts":["I love this!","This is bad"],"user_id":"batch-test"}}'
        </pre>
        
        <h3>3. Get History:</h3>
        <pre style="background: #f4f4f4; padding: 15px; border-radius: 5px;">
curl http://localhost:5000/history?user_id=test&limit=10
        </pre>
        
        <h2>🎨 Frontend:</h2>
        <p>Open <code>frontend/index.html</code> in your browser to use the web interface.</p>
        
        <hr>
        <p style="color: #666;">Press CTRL+C to stop the server</p>
    </body>
    </html>
    '''


if __name__ == '__main__':
    print("=" * 70)
    print("🚀 Sentiment Analysis Local Server Starting...")
    print("=" * 70)
    print()
    print("📂 Project Structure:")
    print("   Root: sentiment-analysis/")
    print("   Backend: backend/")
    print("   Frontend: frontend/")
    print()
    print("📡 API Endpoints:")
    print("   ✅ POST http://localhost:5000/analyze    - Analyze single text")
    print("   ✅ POST http://localhost:5000/batch      - Process multiple texts")
    print("   ✅ GET  http://localhost:5000/history    - Retrieve user history")
    print("   ✅ GET  http://localhost:5000/health     - Health check")
    print()
    print("🎨 Frontend:")
    print("   - Open: frontend/index.html in your browser")
    print("   - All 3 features available:")
    print("     • Analyze Text")
    print("     • Batch Process")
    print("     • History")
    print()
    print("💾 Local Storage:")
    print("   - History stored in memory (resets on restart)")
    print("   - Max 100 items kept")
    print()
    print("=" * 70)
    print("✅ Server running on http://localhost:5000")
    print("Press CTRL+C to stop")
    print("=" * 70)
    print()
    
    app.run(debug=True, port=5000, host='0.0.0.0')