import logging
import time
import psutil
import functools
import traceback
from datetime import datetime
from flask import request, current_app
from logging.handlers import RotatingFileHandler
import json
import os

# Configure logging
def setup_logging():
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(message)s'
    )
    
    # Main application log
    app_handler = RotatingFileHandler(
        'app.log', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_handler.setFormatter(log_formatter)
    app_handler.setLevel(logging.INFO)
    
    # Error log
    error_handler = RotatingFileHandler(
        'error.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    error_handler.setFormatter(log_formatter)
    error_handler.setLevel(logging.ERROR)
    
    # Performance log
    perf_handler = RotatingFileHandler(
        'performance.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    perf_handler.setFormatter(log_formatter)
    perf_handler.setLevel(logging.INFO)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add handlers
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    
    # Create performance logger
    perf_logger = logging.getLogger('performance')
    perf_logger.setLevel(logging.INFO)
    perf_logger.addHandler(perf_handler)
    
    return root_logger, perf_logger

# Initialize loggers
logger, perf_logger = setup_logging()

class Metrics:
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.processing_times = []
    
    def track_request(self, duration):
        self.request_count += 1
        self.processing_times.append(duration)
    
    def track_error(self):
        self.error_count += 1
    
    def get_stats(self):
        uptime = time.time() - self.start_time
        avg_processing_time = sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0
        
        return {
            'uptime': uptime,
            'request_count': self.request_count,
            'error_count': self.error_count,
            'avg_processing_time': avg_processing_time,
            'memory_usage': psutil.Process().memory_info().rss / 1024 / 1024  # MB
        }

# Global metrics instance
metrics = Metrics()

def log_request_metrics():
    """Log request metrics as structured data"""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = f(*args, **kwargs)
                status = getattr(result, 'status_code', 200)
            except Exception as e:
                metrics.track_error()
                status = 500
                raise
            finally:
                duration = time.time() - start_time
                metrics.track_request(duration)
                
                log_data = {
                    'timestamp': datetime.utcnow().isoformat(),
                    'method': request.method,
                    'path': request.path,
                    'status': status,
                    'duration': duration,
                    'ip': request.remote_addr
                }
                
                perf_logger.info(json.dumps(log_data))
            
            return result
        return wrapper
    return decorator

def monitor_resource_usage():
    """Log system resource usage"""
    process = psutil.Process()
    stats = {
        'cpu_percent': process.cpu_percent(),
        'memory_percent': process.memory_percent(),
        'memory_mb': process.memory_info().rss / 1024 / 1024,
        'open_files': len(process.open_files()),
        'threads': process.num_threads()
    }
    perf_logger.info(f"Resource usage: {json.dumps(stats)}")

def handle_error(error):
    """Centralized error handling"""
    metrics.track_error()
    
    error_details = {
        'timestamp': datetime.utcnow().isoformat(),
        'type': error.__class__.__name__,
        'message': str(error),
        'traceback': traceback.format_exc(),
        'path': request.path,
        'method': request.method,
        'ip': request.remote_addr
    }
    
    logger.error(f"Application error: {json.dumps(error_details)}")
    
    if current_app.debug:
        return {'error': str(error), 'traceback': traceback.format_exc()}, 500
    return {'error': 'An internal error occurred'}, 500

# Schedule resource monitoring (called from app initialization)
def start_monitoring(app):
    def monitor():
        with app.app_context():
            monitor_resource_usage()
            
    # Monitor every 5 minutes
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(monitor, 'interval', minutes=5)
    scheduler.start()
    
    return scheduler
