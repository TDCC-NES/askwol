"""Brand assets: Wollie, the hand-drawn owl.

The favicon is embedded as a data URI so every page, including a report saved
to disk, carries it without another request. The larger images are served by
the app under /static (see web.py).
"""

from __future__ import annotations

import base64
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"


def _data_uri(filename: str, mime: str = "image/png") -> str:
    encoded = base64.b64encode((STATIC_DIR / filename).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


FAVICON_LINK = f'<link rel="icon" type="image/png" sizes="32x32" href="{_data_uri("wollie-favicon-32.png")}">'

# Web pages (not saved reports) also offer the larger icon for home screens.
PAGE_ICON_LINKS = FAVICON_LINK + '\n<link rel="apple-touch-icon" href="static/wollie-touch-180.png">'
