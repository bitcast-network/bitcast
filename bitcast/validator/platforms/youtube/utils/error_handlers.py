"""
Standardized error handlers for YouTube platform operations.

This module provides reusable error handling functions for common scenarios
across the YouTube platform module to ensure consistent logging and exception
patterns while reducing code duplication.
"""

from typing import Any, Callable, Dict, Optional

import bittensor as bt
from googleapiclient.errors import HttpError
from requests.exceptions import ConnectionError, RequestException, Timeout
from tenacity import RetryError

from bitcast.validator.utils.error_handling import (
    log_and_raise_api_error,
    log_and_raise_config_error,
    log_and_raise_processing_error,
)

from .helpers import _format_error


def handle_youtube_api_error(
    error: Exception, 
    operation: str, 
    video_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Handle YouTube API errors with specific status code handling.
    
    Args:
        error: The exception that occurred
        operation: Description of the operation that failed
        video_id: Optional video ID for context (will be anonymized)
        additional_context: Additional context information
        
    Raises:
        ConnectionError: For API-related failures
    """
    context = f"YouTube API {operation}"
    params = {"operation": operation}
    
    if video_id:
        params["bitcast_video_id"] = video_id
    
    if additional_context:
        params.update(additional_context)
    
    # Handle specific YouTube API errors
    if isinstance(error, HttpError):
        if error.resp.status == 404:
            bt.logging.warning(f"YouTube API 404 for {operation} - resource not found")
            params["status_code"] = 404
        elif error.resp.status == 403:
            bt.logging.warning(f"YouTube API 403 for {operation} - access denied or quota exceeded")
            params["status_code"] = 403
        elif error.resp.status == 401:
            bt.logging.error(f"YouTube API 401 for {operation} - authentication failed")
            params["status_code"] = 401
        else:
            bt.logging.error(f"YouTube API error {error.resp.status} for {operation}")
            params["status_code"] = error.resp.status
    
    log_and_raise_api_error(
        error=error,
        endpoint="youtube-api",
        params=params,
        context=context
    )


def handle_transcript_api_error(
    error: Exception,
    video_id: str,
    service: str = "rapid-api"
) -> None:
    """
    Handle transcript API errors with service-specific handling.
    
    Args:
        error: The exception that occurred
        video_id: Video ID for context (will be anonymized)
        service: Transcript service name
        
    Raises:
        ConnectionError: For transcript API failures
    """
    context = f"Transcript API ({service})"
    params = {"bitcast_video_id": video_id, "service": service}
    
    # Handle specific transcript error patterns
    if isinstance(error, (ConnectionError, Timeout)):
        bt.logging.warning(f"Transcript API timeout/connection error for video")
    elif isinstance(error, RetryError):
        bt.logging.warning(f"Transcript API retry exhausted for video")
    elif "no subtitles" in str(error).lower():
        bt.logging.info(f"No subtitles available for video")
    else:
        bt.logging.error(f"Transcript API error: {_format_error(error)}")
    
    log_and_raise_api_error(
        error=error,
        endpoint=f"{service}.transcript",
        params=params,
        context=context
    )


def handle_video_data_validation_error(
    error: Exception,
    video_id: str,
    validation_type: str,
    required_fields: Optional[list] = None
) -> None:
    """
    Handle video data validation errors.
    
    Args:
        error: The exception that occurred
        video_id: Video ID for context (will be anonymized)
        validation_type: Type of validation that failed
        required_fields: List of required fields that were missing
        
    Raises:
        RuntimeError: For data validation failures
    """
    context = f"Video data validation ({validation_type})"
    
    if required_fields:
        bt.logging.error(f"Video validation failed: missing required fields {required_fields}")
    else:
        bt.logging.error(f"Video validation failed: {_format_error(error)}")
    
    log_and_raise_processing_error(
        error=error,
        operation=f"video {validation_type} validation",
        context={"bitcast_video_id": video_id, "validation_type": validation_type}
    )


def handle_channel_data_error(
    error: Exception,
    operation: str,
    channel_id: Optional[str] = None
) -> None:
    """
    Handle channel data retrieval/processing errors.
    
    Args:
        error: The exception that occurred
        operation: Description of the channel operation
        channel_id: Optional channel ID for context (will be anonymized)
        
    Raises:
        ConnectionError: For API-related failures
        RuntimeError: For processing failures
    """
    context = f"Channel {operation}"
    params = {"operation": operation}
    
    if channel_id:
        params["bitcast_channel_id"] = channel_id
    
    # Determine if this is an API error or processing error
    if isinstance(error, (HttpError, RequestException, ConnectionError)):
        log_and_raise_api_error(
            error=error,
            endpoint="youtube-api.channel",
            params=params,
            context=context
        )
    else:
        log_and_raise_processing_error(
            error=error,
            operation=f"channel {operation}",
            context=params
        )


def handle_authentication_error(
    error: Exception,
    credential_type: str = "youtube_oauth"
) -> None:
    """
    Handle authentication and credential errors.
    
    Args:
        error: The exception that occurred
        credential_type: Type of credentials that failed
        
    Raises:
        RuntimeError: For configuration errors
    """
    bt.logging.error(f"Authentication failed for {credential_type}: {_format_error(error)}")
    
    log_and_raise_config_error(
        message=f"Failed to authenticate with {credential_type}",
        config_key=credential_type
    )


def handle_analytics_processing_error(
    error: Exception,
    analytics_type: str,
    metric_name: Optional[str] = None,
    fallback_action: Optional[str] = None
) -> None:
    """
    Handle analytics data processing errors.
    
    Args:
        error: The exception that occurred
        analytics_type: Type of analytics (channel, video, etc.)
        metric_name: Specific metric that failed
        fallback_action: Description of fallback action taken
        
    Raises:
        RuntimeError: For processing failures
    """
    context = f"Analytics processing ({analytics_type})"
    
    if fallback_action:
        bt.logging.warning(f"Analytics processing failed for {analytics_type}, {fallback_action}: {_format_error(error)}")
    else:
        bt.logging.error(f"Analytics processing failed for {analytics_type}: {_format_error(error)}")
    
    log_and_raise_processing_error(
        error=error,
        operation=f"{analytics_type} analytics processing",
        context={
            "analytics_type": analytics_type,
            "metric": metric_name,
            "fallback": fallback_action
        }
    )


def safe_api_operation(
    operation_name: str,
    error_handler: Callable[[Exception], None],
    default_return: Any = None,
    log_success: bool = False
):
    """
    Decorator for safely executing API operations with standardized error handling.
    
    Args:
        operation_name: Name of the operation for logging
        error_handler: Function to handle errors (should raise appropriate exception)
        default_return: Value to return on error (if None, re-raises)
        log_success: Whether to log successful operations
        
    Returns:
        Decorator function
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                if log_success:
                    bt.logging.debug(f"Operation '{operation_name}' completed successfully")
                return result
            except Exception as e:
                if default_return is not None:
                    bt.logging.warning(f"Operation '{operation_name}' failed, returning default: {_format_error(e)}")
                    return default_return
                else:
                    error_handler(e)
        return wrapper
    return decorator


def with_retry_error_handling(
    operation_name: str,
    max_retries: int = 3,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    Wrapper for handling retry exhaustion errors consistently.
    
    Args:
        operation_name: Name of the operation
        max_retries: Maximum number of retries attempted
        on_retry: Optional callback for each retry attempt
        
    Returns:
        Context manager for retry error handling
    """
    class RetryErrorHandler:
        def __init__(self, op_name: str, max_ret: int, retry_callback: Optional[Callable]):
            self.operation_name = op_name
            self.max_retries = max_ret
            self.on_retry = retry_callback
            
        def __enter__(self):
            return self
            
        def __exit__(self, exc_type, exc_val, exc_tb):
            if isinstance(exc_val, RetryError):
                bt.logging.error(f"Operation '{self.operation_name}' failed after {self.max_retries} retries")
                return False  # Re-raise the RetryError
            return False
    
    return RetryErrorHandler(operation_name, max_retries, on_retry) 