from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from cleaning_engine import sha256_file
from models import FileRecord


@dataclass(slots=True)
class DiscoveryResult:
    root_path: Path
    files: List[FileRecord] = field(default_factory=list)

    @property
    def discovered_count(self) -> int:
        return len(self.files)


def _iter_folder_files(folder: Path, recursive: bool, supported_extensions: List[str]):
    if recursive:
        iterator = folder.rglob("*")
    else:
        iterator = folder.iterdir()
    for path in iterator:
        if path.is_file() and path.suffix.lower() in supported_extensions:
            yield path


def discover_input_files(config: Dict[str, object]) -> DiscoveryResult:
    root_path = Path(str(config["root_path"]))
    recursive = bool(config.get("recursive_scan", False))
    supported_extensions = [str(ext).lower() for ext in config.get("supported_extensions", [])]
    input_folders = config.get("input_folders", {})

    files: List[FileRecord] = []
    batch_id = str(config.get("batch_id", ""))

    for source_type, folder_name in input_folders.items():
        folder_path = root_path / str(folder_name)
        if not folder_path.exists():
            continue
        for file_path in sorted(_iter_folder_files(folder_path, recursive, supported_extensions), key=lambda item: str(item).lower()):
            stats = file_path.stat()
            files.append(
                FileRecord(
                    batch_id=batch_id,
                    source_type=str(source_type),
                    folder_name=str(folder_name),
                    file_name=file_path.name,
                    file_path=file_path,
                    file_hash=sha256_file(file_path),
                    file_size=stats.st_size,
                    modified_at=datetime.fromtimestamp(stats.st_mtime).isoformat(timespec="seconds"),
                )
            )

    return DiscoveryResult(root_path=root_path, files=files)
