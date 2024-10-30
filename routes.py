from flask import render_template, request, jsonify
from app import app, logger
from error_handling.exceptions import TranscriptionError
import traceback
from datetime import datetime
from transcription.deepgram_streaming import DeepgramStreamingClient
from flask_sock import Sock

# Initialize Flask-Sock for WebSocket support
sock = Sock(app)

# Initialize Deepgram streaming client
streaming_client = DeepgramStreamingClient()

@app.route('/')
def index():
    """Main page route handler"""
    logger.info("Serving index page")
    return render_template('transcribe.html')

@app.route('/vocabulary')
def vocabulary():
    """Custom vocabulary page route handler"""
    logger.info("Serving vocabulary page")
    return render_template('vocabulary.html')

@sock.route('/stream')
async def stream(ws):
    """WebSocket endpoint for real-time transcription"""
    logger.info("New streaming connection initiated")
    try:
        await streaming_client.handle_websocket(ws)
    except Exception as e:
        logger.error(f"Streaming error: {str(e)}\n{traceback.format_exc()}")
        try:
            await ws.send(str(e))
        except:
            pass

@app.route('/api/log-error', methods=['POST'])
def log_frontend_error():
    """Frontend error logging endpoint with enhanced error handling"""
    try:
        error_data = request.get_json()
        if not error_data:
            return jsonify({'error': 'No error data provided'}), 400
            
        # Add timestamp and request context
        error_data.update({
            'timestamp': datetime.utcnow().isoformat(),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent'),
            'path': request.headers.get('Referer')
        })
        
        logger.error(f"Frontend error: {error_data}")
        return jsonify({'status': 'error logged'})
    except Exception as e:
        logger.error(f"Error logging frontend error: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to log error'}), 500

@app.route('/api/log-event', methods=['POST'])
def log_frontend_event():
    """Frontend event logging endpoint with validation"""
    try:
        event_data = request.get_json()
        if not event_data:
            return jsonify({'error': 'No event data provided'}), 400
            
        required_fields = ['category', 'action']
        missing_fields = [field for field in required_fields if field not in event_data]
        
        if missing_fields:
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
            
        # Add timestamp and request context
        event_data.update({
            'timestamp': datetime.utcnow().isoformat(),
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent')
        })
        
        logger.info(f"Frontend event: {event_data}")
        return jsonify({'status': 'event logged'})
    except Exception as e:
        logger.error(f"Error logging frontend event: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to log event'}), 500
