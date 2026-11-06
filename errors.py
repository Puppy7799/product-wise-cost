"""Application-specific exceptions."""


class ExpenseManagerError(Exception):
    """Base class for expected application errors."""


class ValidationError(ExpenseManagerError):
    """Raised when user-provided data is invalid."""


class ConfigurationError(ExpenseManagerError):
    """Raised when application configuration is invalid or unreadable."""


class DataFileError(ExpenseManagerError):
    """Raised when a CSV data file cannot be read or written."""


class StorageError(ExpenseManagerError):
    """Raised when ledger storage cannot complete an operation."""
