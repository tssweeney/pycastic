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


class RefactoringError(PyfactorError):
    """Error during rope refactoring operation."""

    pass


class ProjectError(PyfactorError):
    """Error with project configuration or access."""

    pass
