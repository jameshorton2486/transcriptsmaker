from flask import render_template
from app import app, logger

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

@app.route('/api/log-error', methods=['POST'])
def log_frontend_error():
    """Frontend error logging endpoint"""
    try:
        error_data = request.get_json()
        logger.error(f"Frontend error: {error_data}")
        return jsonify({'status': 'error logged'})
    except Exception as e:
        logger.error(f"Error logging frontend error: {str(e)}")
        return jsonify({'error': 'Failed to log error'}), 500
