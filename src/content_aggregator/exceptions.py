class RateLimitExceededError(Exception):
    """Exception raised when API rate limits are exceeded"""
    def __init__(self, message="API rate limit exceeded", retry_after=None):
        self.retry_after = retry_after  # Optional retry time in seconds
        super().__init__(f"{message}. Retry after: {retry_after}s" if retry_after else message) 