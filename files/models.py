"""Shared types for file broker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class FetchedFile:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    source: str = ""
    path: str = ""


@dataclass
class ListedEntry:
    name: str
    path: str
    type: Literal["dir", "file"]
    bytes: Optional[int] = None


class SourceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
