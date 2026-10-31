"""Exceptions raised by the MyENGIE client."""

from __future__ import annotations


class EngieError(Exception):
    """Base ENGIE exception."""


class EngieAuthError(EngieError):
    """Credentials rejected, or the session could not be renewed."""


class EngieConnectionError(EngieError):
    """The API could not be reached or did not answer in time."""


class EngieRejectedError(EngieError):
    """ENGIE refused a submission; the message is ENGIE's own reason."""
