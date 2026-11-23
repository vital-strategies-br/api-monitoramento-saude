import hashlib


def split_csv(value: str) -> list[str]:
    """Split a comma-separated setting into trimmed, non-empty items."""
    return [item.strip() for item in value.split(",") if item.strip()]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
