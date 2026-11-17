"""Verified TLS context for MAX's Russian Trusted CA certificate chain."""

from __future__ import annotations

import ssl
from pathlib import Path


def max_tls_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    root = Path(__file__).resolve().parent.parent / "certs" / "russian-trusted-root.pem"
    context.load_verify_locations(cafile=str(root))
    return context
