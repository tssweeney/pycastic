"""
Custom exceptions for pyfactor.
"""


class PyfactorError(Exception):
    """Base exception for pyfactor errors."""

    pass


class TargetParseError(PyfactorError):
    """Error parsing target specification."""

    pass


class SymbolNotFoundError(PyfactorError):
    """Symbol could not be found in the specified file."""

    pass


class AmbiguousSymbolError(PyfactorError):
    """Multiple symbols with the same name exist.

    This error includes information about all matching symbols
    to help the user disambiguate.
    """

    def __init__(self, message: str, matches: list = None):
        super().__init__(message)
        self.matches = matches or []


class RefactoringError(PyfactorError):
    """Error during refactoring operation."""

    pass


class CircularDependencyError(PyfactorError):
    """Raised when moving a symbol would create a circular import.

    This occurs when a symbol depends on another symbol in the same file
    that is also used by symbols that are NOT being moved.
    """

    def __init__(self, message: str, shared_symbols: list[str] = None):
        super().__init__(message)
        self.shared_symbols = shared_symbols or []


class ProjectError(PyfactorError):
    """Error with project configuration or access."""

    pass
