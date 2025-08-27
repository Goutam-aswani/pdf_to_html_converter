class PDFProcessingError(Exception):
    """Base exception class for PDF processing errors."""
    def __init__(self, message="An error occurred during PDF processing"):
        self.message = message
        super().__init__(self.message)

class InvalidPDFError(PDFProcessingError):
    """Raised when the file is not a valid or readable PDF."""
    def __init__(self, message="The provided file is not a valid PDF or is corrupted."):
        super().__init__(message)

class PasswordProtectedPDFError(PDFProcessingError):
    """Raised when a PDF is password-protected but no password is provided or it's incorrect."""
    def __init__(self, message="The PDF is password-protected. Please provide a valid password."):
        super().__init__(message)