class AppException(Exception):
    status_code: int = 500
    message: str = "An unexpected error occurred"

    def __init__(self, message: str | None = None):
        self.message = message or self.__class__.message
        super().__init__(self.message)


class ClaimNotFoundException(AppException):
    status_code = 404
    message = "Claim not found"


class MemberNotFoundException(AppException):
    status_code = 404
    message = "Member not found"


class ProviderNotFoundException(AppException):
    status_code = 404
    message = "Provider not found"


class ValidationException(AppException):
    status_code = 422
    message = "Validation failed"
