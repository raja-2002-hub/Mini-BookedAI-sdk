"""
Duffel API client for travel search functionality.
"""

from .client import DuffelClient
from .endpoints.stays import StaysEndpoint

__all__ = ["DuffelClient", "StaysEndpoint"] 