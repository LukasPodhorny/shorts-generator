from pathlib import Path


def resolve_path(path: str | None) -> str | None:
    """Make path absolute based on current working directory."""
    if not path:
        return path
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    return str(p.resolve())
