"""
Custom exceptions for pycastic.
"""


class PycasticError(Exception):
    """Base exception for pycastic errors."""

    pass


class TargetParseError(PycasticError):
    """Error parsing target specification."""

    pass


class SymbolNotFoundError(PycasticError):
    """Symbol could not be found in the specified file."""

    pass


class AmbiguousSymbolError(PycasticError):
    """Multiple symbols with the same name exist.

    This error includes information about all matching symbols
    to help the user disambiguate.
    """

    def __init__(self, message: str, matches: list = None):
        super().__init__(message)
        self.matches = matches or []


class RefactoringError(PycasticError):
    """Error during refactoring operation."""

    pass


class CircularDependencyError(PycasticError):
    """Raised when moving a symbol would create a circular import.

    This occurs when a symbol depends on another symbol in the same file
    that is also used by symbols that are NOT being moved.
    """

    def __init__(self, message: str, shared_symbols: list[str] = None):
        super().__init__(message)
        self.shared_symbols = shared_symbols or []


class ProjectError(PycasticError):
    """Error with project configuration or access."""

    pass
