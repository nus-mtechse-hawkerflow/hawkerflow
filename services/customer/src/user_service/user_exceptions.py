class UserException(Exception):
    """Error carrying an HTTP status, raised from any layer and mapped by handlers."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message
