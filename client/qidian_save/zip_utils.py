"""Utilities for safely extracting zip files returned by the server."""
from pathlib import Path
import zipfile


class UnsafeZipPathError(ValueError):
    """Raised when a zip member would extract outside the target directory."""


def _safe_member_path(output_dir: Path, member_name: str) -> Path:
    target_root = output_dir.resolve()
    member_path = Path(member_name)

    if member_path.is_absolute():
        raise UnsafeZipPathError(f"Unsafe absolute zip path: {member_name}")

    target = (target_root / member_path).resolve()
    if target != target_root and target_root not in target.parents:
        raise UnsafeZipPathError(f"Unsafe zip path traversal: {member_name}")
    return target


def safe_extract_zip(zf: zipfile.ZipFile, output_dir: str | Path) -> list[Path]:
    """Extract all zip members after verifying they stay under output_dir."""
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    for info in zf.infolist():
        target = _safe_member_path(output_root, info.filename)
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, target.open("wb") as dst:
            dst.write(src.read())
        extracted.append(target)
    return extracted
