import logging
import time
import psutil
import functools
import traceback
from datetime import datetime
from flask import request, current_app, g
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import json
import os
import atexit
from typing import Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Enhanced logging configuration
def setup_logging():
    log_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - [%(module)s:%(lineno)d] - %(message)s'
    )
    
    # Main application log with size-based rotation
    app_handler = RotatingFileHandler(
        'app.log', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    app_handler.setFormatter(log_formatter)
    app_handler.setLevel(logging.INFO)
    
    # Error log with time-based rotation
    error_handler = TimedRotatingFileHandler(
        'error.log',
        when='midnight',
        interval=1,
        backupCount=30
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

class MetricsCollector:
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.processing_times: Dict[str, list] = {}
        self.endpoint_stats: Dict[str, Dict[str, Any]] = {}
        self.error_types: Dict[str, int] = {}
        
    def track_request(self, endpoint: str, duration: float, status_code: int):
        self.request_count += 1
        
        if endpoint not in self.processing_times:
            self.processing_times[endpoint] = []
        self.processing_times[endpoint].append(duration)
        
        if endpoint not in self.endpoint_stats:
            self.endpoint_stats[endpoint] = {
                'count': 0,
                'errors': 0,
                'total_time': 0
            }
        
        self.endpoint_stats[endpoint]['count'] += 1
        self.endpoint_stats[endpoint]['total_time'] += duration
        
        if status_code >= 400:
            self.endpoint_stats[endpoint]['errors'] += 1
    
    def track_error(self, error_type: str):
        self.error_count += 1
        self.error_types[error_type] = self.error_types.get(error_type, 0) + 1
    
    def get_stats(self) -> Dict[str, Any]:
        process = psutil.Process()
        
        stats = {
            'system': {
                'uptime': time.time() - self.start_time,
                'cpu_percent': process.cpu_percent(),
                'memory_usage_mb': process.memory_info().rss / 1024 / 1024,
                'open_files': len(process.open_files()),
                'threads': process.num_threads()
            },
            'requests': {
                'total_count': self.request_count,
                'error_count': self.error_count,
                'error_types': self.error_types
            },
            'endpoints': {}
        }
        
        # Calculate endpoint-specific metrics
        for endpoint, times in self.processing_times.items():
            avg_time = sum(times) / len(times) if times else 0
            stats['endpoints'][endpoint] = {
                'count': self.endpoint_stats[endpoint]['count'],
                'errors': self.endpoint_stats[endpoint]['errors'],
                'avg_response_time': avg_time,
                'min_response_time': min(times) if times else 0,
                'max_response_time': max(times) if times else 0
            }
        
        return stats

# Global metrics instance
metrics = MetricsCollector()

def log_request_metrics():
    """Enhanced request metrics logging decorator"""
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            endpoint = request.endpoint or 'unknown'
            
            try:
                g.request_id = str(int(time.time() * 1000))  # Unique request ID
                result = f(*args, **kwargs)
                status_code = getattr(result, 'status_code', 200)
                
                return result
            except Exception as e:
                metrics.track_error(e.__class__.__name__)
                status_code = 500
                raise
            finally:
                duration = time.time() - start_time
                metrics.track_request(endpoint, duration, status_code)
                
                log_data = {
                    'request_id': g.request_id,
                    'timestamp': datetime.utcnow().isoformat(),
                    'method': request.method,
                    'endpoint': endpoint,
                    'path': request.path,
                    'status': status_code,
                    'duration': duration,
                    'ip': request.remote_addr,
                    'user_agent': request.headers.get('User-Agent'),
                }
                
                perf_logger.info(json.dumps(log_data))
                
        return wrapper
    return decorator

def monitor_resource_usage():
    """Enhanced system resource monitoring"""
    process = psutil.Process()
    
    # System metrics
    system_stats = {
        'cpu': {
            'system': psutil.cpu_percent(interval=1),
            'process': process.cpu_percent(),
            'cores': psutil.cpu_count()
        },
        'memory': {
            'total': psutil.virtual_memory().total / (1024 * 1024 * 1024),  # GB
            'available': psutil.virtual_memory().available / (1024 * 1024 * 1024),  # GB
            'process': process.memory_info().rss / (1024 * 1024),  # MB
            'percent': process.memory_percent()
        },
        'disk': {
            'total': psutil.disk_usage('/').total / (1024 * 1024 * 1024),  # GB
            'free': psutil.disk_usage('/').free / (1024 * 1024 * 1024),  # GB
            'percent': psutil.disk_usage('/').percent
        },
        'process': {
            'open_files': len(process.open_files()),
            'threads': process.num_threads(),
            'connections': len(process.connections())
        }
    }
    
    perf_logger.info(f"Resource usage: {json.dumps(system_stats)}")
    
    # Alert on high resource usage
    if system_stats['cpu']['process'] > 80:
        logger.warning("High CPU usage detected")
    if system_stats['memory']['percent'] > 80:
        logger.warning("High memory usage detected")
    if system_stats['disk']['percent'] > 90:
        logger.warning("Low disk space warning")

def start_monitoring(app):
    """Initialize monitoring scheduler with multiple jobs"""
    scheduler = BackgroundScheduler()
    
    # Resource monitoring every 5 minutes
    scheduler.add_job(
        lambda: monitor_resource_usage(),
        trigger=CronTrigger(minute='*/5'),
        id='resource_monitor'
    )
    
    # Daily metrics report
    def daily_report():
        stats = metrics.get_stats()
        logger.info(f"Daily metrics report: {json.dumps(stats)}")
    
    scheduler.add_job(
        daily_report,
        trigger=CronTrigger(hour=0, minute=0),
        id='daily_report'
    )
    
    # Start the scheduler
    scheduler.start()
    
    # Register cleanup
    atexit.register(lambda: scheduler.shutdown())
    
    return scheduler
