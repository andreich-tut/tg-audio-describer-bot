try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("tg-voice")
except PackageNotFoundError:
    # Fallback: read directly from pyproject.toml
    import re
    from pathlib import Path

    _pyproject = Path(__file__).parent / "pyproject.toml"
    _match = re.search(r'^version\s*=\s*"([^"]+)"', _pyproject.read_text(), re.MULTILINE)
    __version__ = _match.group(1) if _match else "unknown"
