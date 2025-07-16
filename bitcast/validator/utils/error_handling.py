"""
Error handling utilities for consistent error patterns across the validator.

This module provides simple helper functions to standardize error handling
and logging patterns throughout the codebase.
"""

import bittensor as bt
from typing import Any, Dict, Optional


def log_and_raise_api_error(
    error: Exception, 
    endpoint: str, 
    params: Optional[Dict[str, Any]] = None,
    context: str = "API call"
) -> None:
    """
    Log API error with context and raise ConnectionError.
    
    Args:
        error: The original exception
        endpoint: API endpoint that failed
        params: Request parameters (will be sanitized)
        context: Additional context for the error
        
    Raises:
        ConnectionError: Always raises with formatted message
    """
    # Sanitize params to avoid logging sensitive data
    safe_params = {}
    if params:
        safe_params = {k: v for k, v in params.items() 
                      if k.lower() not in ['api_key', 'token', 'password', 'secret']}
    
    bt.logging.error(
        f"{context} failed: {error}",
        extra={
            'endpoint': endpoint,
            'params': safe_params,
            'error_type': type(error).__name__
        }
    )
    raise ConnectionError(f"{context} failed for {endpoint}: {error}")


def log_and_raise_validation_error(
    message: str,
    data: Optional[Dict[str, Any]] = None,
    context: str = "Data validation"
) -> None:
    """
    Log validation error with context and raise ValueError.
    
    Args:
        message: Error message describing what validation failed
        data: Data that failed validation (will be truncated if large)
        context: Additional context for the error
        
    Raises:
        ValueError: Always raises with formatted message
    """
    # Truncate large data for logging
    safe_data = data
    if data and len(str(data)) > 200:
        safe_data = str(data)[:200] + "... (truncated)"
    
    bt.logging.error(
        f"{context} failed: {message}",
        extra={
            'validation_data': safe_data,
            'error_type': 'ValidationError'
        }
    )
    raise ValueError(f"{context} failed: {message}")


def log_and_raise_processing_error(
    error: Exception,
    operation: str,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log processing error with context and raise RuntimeError.
    
    Args:
        error: The original exception
        operation: Description of the operation that failed
        context: Additional context information
        
    Raises:
        RuntimeError: Always raises with formatted message
    """
    bt.logging.error(
        f"Processing operation '{operation}' failed: {error}",
        extra={
            'operation': operation,
            'context': context,
            'error_type': type(error).__name__
        }
    )
    raise RuntimeError(f"Processing operation '{operation}' failed: {error}")


def log_and_raise_config_error(
    message: str,
    config_key: Optional[str] = None,
    config_value: Optional[str] = None
) -> None:
    """
    Log configuration error and raise RuntimeError.
    
    Args:
        message: Error message describing the configuration issue
        config_key: The configuration key that's problematic
        config_value: The problematic value (will be sanitized)
        
    Raises:
        RuntimeError: Always raises with formatted message
    """
    # Sanitize config value
    safe_value = config_value
    if config_value and any(sensitive in str(config_key).lower() 
                           for sensitive in ['key', 'token', 'password', 'secret']):
        safe_value = '***REDACTED***'
    
    bt.logging.error(
        f"Configuration error: {message}",
        extra={
            'config_key': config_key,
            'config_value': safe_value,
            'error_type': 'ConfigurationError'
        }
    )
    raise RuntimeError(f"Configuration error: {message}")


def safe_operation(operation_name: str, default_return=None):
    """
    Decorator to safely execute operations with consistent error logging.
    
    Args:
        operation_name: Name of the operation for logging
        default_return: Value to return on error (if None, re-raises)
        
    Returns:
        Decorator function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                bt.logging.error(
                    f"Operation '{operation_name}' failed: {e}",
                    extra={
                        'operation': operation_name,
                        'function': func.__name__,
                        'error_type': type(e).__name__
                    }
                )
                if default_return is not None:
                    return default_return
                raise
        return wrapper
    return decorator


# Standard error messages for common scenarios
class ErrorMessages:
    """Standard error messages for consistency."""
    
    # API-related errors
    API_CONNECTION_FAILED = "Failed to connect to API"
    API_RATE_LIMITED = "API rate limit exceeded"
    API_INVALID_RESPONSE = "API returned invalid response"
    API_TIMEOUT = "API request timed out"
    
    # Validation errors
    INVALID_VIDEO_ID = "Invalid or missing video ID"
    INVALID_CHANNEL_ID = "Invalid or missing channel ID"
    MISSING_REQUIRED_FIELD = "Required field is missing"
    INVALID_DATA_FORMAT = "Data format is invalid"
    
    # Processing errors
    EVALUATION_FAILED = "Video evaluation process failed"
    SCORING_FAILED = "Scoring calculation failed"
    CACHE_OPERATION_FAILED = "Cache operation failed"
    
    # Configuration errors
    MISSING_CONFIG = "Required configuration is missing"
    INVALID_CONFIG = "Configuration value is invalid"
    CREDENTIALS_MISSING = "Required credentials are missing" 