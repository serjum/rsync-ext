class RsyncExtError(Exception):
    pass


class ValidationError(RsyncExtError):
    pass


class TransferError(RsyncExtError):
    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.details = details or ""

