"""
Helper utility functions for YouTube evaluation.

This module contains general-purpose utility functions used across
the YouTube evaluation system.
"""

import re


def _format_error(e):
    """Format error message to include only error type and brief summary."""
    et = type(e).__name__
    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
        return f"{et} ({e.response.status_code})"
    if hasattr(e, 'error') and isinstance(e.error, dict):
        details = e.error.get('details', [{}])[0].get('message', 'unknown error')
        return f"{et} ({details})"
    msg = re.sub(r'https?://\S+', '', str(e)).split('\n')[0].strip()
    return f"{et} ({msg})" 