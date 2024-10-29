"""Error handling utilities and decorators."""

import logging
import functools
import traceback
from typing import Type, Callable
from contextlib import contextmanager
from .exceptions import TranscriptionError, DatabaseError, ProcessingError
from flask import current_app, jsonify
import time

logger = logging.getLogger(__name__)

def handle_errors(error_map=None):
    """
    Decorator for handling exceptions with custom mapping.
    
    Args:
        error_map: Dictionary mapping exception types to handler functions
    """
    if error_map is None:
        error_map = {}
        
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Find the most specific handler
                for exc_type, handler in error_map.items():
                    if isinstance(e, exc_type):
                        return handler(e)
                
                # Default error handling if no specific handler found
                logger.error(f"Unhandled exception in {func.__name__}: {str(e)}")
                if isinstance(e, TranscriptionError):
                    return jsonify(e.to_dict()), getattr(e, 'status_code', 500)
                
                return jsonify({
                    'error_code': 'INTERNAL_ERROR',
                    'message': 'An unexpected error occurred',
                    'type': e.__class__.__name__
                }), 500
        return wrapper
    return decorator

@contextmanager
def error_context(context_name: str, error_class: Type[Exception] = ProcessingError):
    """Context manager for handling errors with additional context."""
    start_time = time.time()
    try:
        yield
    except Exception as e:
        logger.error(f"Error in {context_name}: {str(e)}")
        if isinstance(e, TranscriptionError):
            raise
        raise error_class(f"Error in {context_name}: {str(e)}") from e
    finally:
        duration = time.time() - start_time
        logger.info(f"Completed {context_name} in {duration:.2f} seconds")

def retry_on_error(max_retries: int = 3, delay: float = 1.0, 
                  allowed_exceptions: tuple = (DatabaseError,)):
    """Decorator for retrying operations on specific exceptions."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except allowed_exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {str(e)}")
                        time.sleep(delay * (attempt + 1))
                    continue
                except Exception as e:
                    raise
            
            logger.error(f"All {max_retries} retries failed for {func.__name__}")
            raise last_exception
        return wrapper
    return decorator

def log_errors(logger_instance: logging.Logger = None):
    """Decorator for logging exceptions with detailed information."""
    if logger_instance is None:
        logger_instance = logger
        
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger_instance.error(
                    f"Error in {func.__name__}: {str(e)}\n"
                    f"Traceback:\n{traceback.format_exc()}"
                )
                raise
        return wrapper
    return decorator
