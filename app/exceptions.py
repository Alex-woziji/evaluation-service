class EvaluationError(Exception):
    """Base class for all evaluation errors."""
    pass

class ConfigValidationError(EvaluationError):
    """Raised when metric-level config validation fails."""
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field

class ParseError(EvaluationError):
    """Raised when LLM response cannot be parsed. No retry."""
    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.message = message
        self.raw_response = raw_response

class LLMAPIError(EvaluationError):
    """Raised when LLM API returns an error that exhausts retries."""
    def __init__(self, message: str, retry_count: int = 0):
        super().__init__(message)
        self.message = message
        self.retry_count = retry_count

class LLMTimeoutError(EvaluationError):
    """Raised when LLM API times out and exhausts retries."""
    def __init__(self, message: str, retry_count: int = 0):
        super().__init__(message)
        self.message = message
        self.retry_count = retry_count
