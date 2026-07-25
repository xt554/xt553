class DomainError(ValueError):
    def __init__(self, message: str, code: str = "DOMAIN_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(DomainError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, "NOT_FOUND")


class ConflictError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "CONFLICT")


class ValidationError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "VALIDATION_ERROR")
