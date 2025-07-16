"""Custom exceptions for score and emission calculation errors."""


class ScoreCalculationError(Exception):
    """Base exception for score calculation errors."""
    pass


class EmissionCalculationError(Exception):
    """Base exception for emission calculation errors."""
    pass 