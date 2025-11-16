"""Utilities for ensuring local data files are present."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

logger = logging.getLogger(__name__)


def ensure_data_file(path: str | Path, source_url: str | None = None) -> Path:
    """Ensure a data file exists locally, downloading it when a URL is provided."""
    file_path = Path(path)
    if file_path.exists():
        return file_path
    if not source_url:
        raise FileNotFoundError(
            f"Required data file missing and no download URL provided: {file_path}"
        )
    logger.info("Downloading %s from %s", file_path, source_url)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(source_url) as response, file_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except (OSError, URLError) as exc:
        raise RuntimeError(f"Failed to download {source_url} -> {file_path}") from exc
    return file_path
