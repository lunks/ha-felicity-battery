"""SSL context for the Felicity API.

The Felicity API server at shine-api.felicitysolar.com serves only its leaf
certificate, omitting the "Xcc Trust OV SSL CA" intermediate. That intermediate
is issued by "Certum Trusted Network CA", which IS in Python's default CA
bundle. We bundle the missing intermediate so verification succeeds without
trusting any new root.
"""

from __future__ import annotations

import ssl
from functools import lru_cache
from pathlib import Path

_INTERMEDIATE_PEM = Path(__file__).parent / "xcc_trust_intermediate.pem"


@lru_cache(maxsize=1)
def get_ssl_context() -> ssl.SSLContext:
    """Return an SSLContext with the bundled Xcc Trust intermediate loaded."""
    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cafile=str(_INTERMEDIATE_PEM))
    return ctx
