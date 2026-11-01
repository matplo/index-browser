"""index-browser: turn a directory tree into an interactive 3D index.html."""

__version__ = "0.3.0"

from .core import IndexBrowserError, Result, build, scan  # noqa: E402

__all__ = ["IndexBrowserError", "Result", "build", "scan", "__version__"]
