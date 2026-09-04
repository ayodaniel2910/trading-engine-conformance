"""Path containment: reject traversal, absolute paths, and symlink escape.

``resolve_contained`` is the single entry point every other integrity
module uses to turn a manifest-declared relative path into a real
filesystem path. A relative path is only accepted if it is portable (see
``trading_engine_conformance.schema.types.PortableRelPath``), its final
component is not itself a symlink/reparse point, and -- after resolving any
symlinked parent directories -- it still lives inside the declared root.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from trading_engine_conformance.schema.types import PortableRelPath

_PORTABLE_PATH_ADAPTER: TypeAdapter[str] = TypeAdapter(PortableRelPath)


class PathContainmentError(ValueError):
    """Raised when a relative path is not portable or would escape its root."""


def resolve_contained(root: Path, relative_path: str) -> Path:
    """Resolve ``relative_path`` under ``root``.

    Raises ``PathContainmentError`` if ``relative_path`` is not a portable
    relative path, its final component is a symlink/reparse point, or the
    resolved path (following any symlinked parent directories) does not
    live inside ``root``. ``root`` itself must already exist.
    """
    try:
        validated = _PORTABLE_PATH_ADAPTER.validate_python(relative_path)
    except PydanticValidationError as exc:
        raise PathContainmentError(f"not a portable relative path: {relative_path!r}") from exc

    root_resolved = root.resolve(strict=True)
    candidate = root_resolved.joinpath(*validated.split("/"))

    if candidate.is_symlink():
        raise PathContainmentError(f"path is a symlink, refusing to follow it: {relative_path!r}")

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise PathContainmentError(
            f"path escapes its root after resolution: {relative_path!r}"
        ) from exc
    return resolved
