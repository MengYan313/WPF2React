"""Shared cross-cutting infrastructure."""

from .logging import AppLogger, get_logger

__all__ = ["AppLogger", "get_logger"]
