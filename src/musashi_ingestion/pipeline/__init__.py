"""Durable normalized records and delivery queue."""

from .spool import Spool, SpoolError, make_record

__all__ = ["Spool", "SpoolError", "make_record"]
