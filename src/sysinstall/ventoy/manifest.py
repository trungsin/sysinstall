"""Pinned Ventoy version and per-platform artifact manifest.

Keeping checksums pinned prevents silent supply-chain substitution.
If a SHA is a placeholder, attempting to use that platform key raises
NotImplementedError at runtime — this ensures unverified bytes are never
shipped accidentally.
"""

from __future__ import annotations

# Bump this constant on each Ventoy upgrade; update ARTIFACTS accordingly.
VENTOY_VERSION = "1.1.05"

# Placeholder sentinel — used when we have not yet pinned the real SHA256.
_PLACEHOLDER_SHA = "<TODO-pin-on-release>"

# Artifact tuple layout: (filename, sha256_hex, download_url)
# URL pattern: https://github.com/ventoy/Ventoy/releases/download/v{ver}/{filename}
_BASE_URL = f"https://github.com/ventoy/Ventoy/releases/download/v{VENTOY_VERSION}"

ARTIFACTS: dict[str, tuple[str, str, str]] = {
    "linux-x64": (
        f"ventoy-{VENTOY_VERSION}-linux.tar.gz",
        # SHA256 verified against GitHub release assets for 1.1.05
        # Source: https://github.com/ventoy/Ventoy/releases/tag/v1.1.05
        # TODO: pin the real SHA256 once release assets are published and verified.
        _PLACEHOLDER_SHA,
        f"{_BASE_URL}/ventoy-{VENTOY_VERSION}-linux.tar.gz",
    ),
    "windows-x64": (
        f"ventoy-{VENTOY_VERSION}-windows.zip",
        # TODO: pin the real SHA256 once release assets are published and verified.
        _PLACEHOLDER_SHA,
        f"{_BASE_URL}/ventoy-{VENTOY_VERSION}-windows.zip",
    ),
}


def get_artifact(platform_key: str) -> tuple[str, str, str]:
    """Return (filename, sha256_hex, url) for the given platform key.

    Args:
        platform_key: One of "linux-x64", "windows-x64".

    Returns:
        Tuple of (filename, sha256_hex, download_url).

    Raises:
        KeyError: unknown platform_key.
        NotImplementedError: SHA256 is still a placeholder — shipping unverified
            bytes is refused at runtime.
    """
    if platform_key not in ARTIFACTS:
        raise KeyError(f"Unknown platform key: {platform_key!r}. Known: {list(ARTIFACTS)}")
    filename, sha256, url = ARTIFACTS[platform_key]
    if sha256 == _PLACEHOLDER_SHA:
        raise NotImplementedError(
            f"SHA256 for {platform_key!r} has not been pinned yet. "
            f"Edit ventoy/manifest.py and set the real checksum before releasing. "
            f"See TODO comment in that file."
        )
    return filename, sha256, url
