
class RunnerFailure(RuntimeError):
    def __init__(self, message: str, *, kind: str, retryable: bool, manual_review: bool = False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable
        self.manual_review = manual_review


class LoginRequired(RunnerFailure):
    def __init__(self, message: str = "Fragment login is required"):
        super().__init__(message, kind="LOGIN_REQUIRED", retryable=False, manual_review=True)


class SelectorFailure(RunnerFailure):
    def __init__(self, message: str):
        super().__init__(message, kind="SELECTOR_ERROR", retryable=False, manual_review=True)
