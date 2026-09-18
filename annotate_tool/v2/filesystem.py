from pathlib import Path
import shutil


def publish_directory(source: Path, destination: Path, source_root: Path, destination_root: Path) -> None:
    resolved_source = source.resolve(strict=True)
    resolved_destination = destination.resolve(strict=False)
    if resolved_source.parent != source_root.resolve() or resolved_destination.parent != destination_root.resolve():
        raise ValueError("publish paths must be direct children of their configured roots")
    if resolved_destination.exists():
        raise FileExistsError(resolved_destination)
    try:
        resolved_source.replace(resolved_destination)
    except PermissionError:
        try:
            shutil.copytree(resolved_source, resolved_destination)
            shutil.rmtree(resolved_source)
        except Exception:
            if resolved_destination.exists():
                shutil.rmtree(resolved_destination)
            raise
