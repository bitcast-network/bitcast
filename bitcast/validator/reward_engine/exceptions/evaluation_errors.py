"""Custom exceptions for platform evaluation errors."""


class EvaluationError(Exception):
    """Base exception for evaluation errors."""
    pass


class PlatformNotSupportedError(EvaluationError):
    """Raised when a platform is not supported by any evaluator."""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        super().__init__(f"Platform '{platform_name}' is not supported")


class InvalidTokenError(EvaluationError):
    """Raised when an access token is invalid or malformed."""
    
    def __init__(self, token_type: str, reason: str = ""):
        self.token_type = token_type
        self.reason = reason
        message = f"Invalid {token_type} token"
        if reason:
            message += f": {reason}"
        super().__init__(message) 