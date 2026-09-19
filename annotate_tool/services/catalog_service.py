from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid

from annotate_tool.config import ImportLimits
from annotate_tool.reference_catalog import (
    ReferenceCatalogError,
    ReferenceCatalogStorageError,
    import_reference_catalog,
)
from annotate_tool.repositories.catalogs import CatalogRecord, CatalogRepository
from annotate_tool.v2.config import V2Paths
from annotate_tool.v2.filesystem import publish_directory


class CatalogImportError(ValueError):
    pass


class CatalogStorageError(RuntimeError):
    pass


class CatalogService:
    def __init__(self, paths: V2Paths, repository: CatalogRepository, limits: ImportLimits):
        self.paths = paths
        self.repository = repository
        self.limits = limits

    def import_catalog(self, name: str, zip_path: Path) -> CatalogRecord:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise CatalogImportError("Catalog name is required")
        catalog_id = uuid.uuid4().hex
        staged_root = self.paths.staging / f"catalog-{catalog_id}"
        final_root = self.paths.catalogs / catalog_id
        published = False
        try:
            classes = import_reference_catalog(zip_path, staged_root, self.limits)
            (staged_root / ".catalog_complete").replace(staged_root / ".complete")
            publish_directory(staged_root, final_root, self.paths.staging, self.paths.catalogs)
            published = True
            created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            self.repository.create(
                catalog_id=catalog_id,
                name=cleaned_name,
                storage_root=final_root,
                classes=tuple(
                    (item.class_id, item.name, final_root / "images" / item.reference_path.name)
                    for item in classes
                    if item.reference_path is not None
                ),
                created_at=created_at,
            )
            return self.repository.get(catalog_id)
        except ReferenceCatalogStorageError as exc:
            raise CatalogStorageError("Catalog storage operation failed") from exc
        except ReferenceCatalogError as exc:
            raise CatalogImportError(str(exc)) from exc
        except OSError as exc:
            raise CatalogStorageError("Catalog storage operation failed") from exc
        finally:
            if staged_root.exists():
                shutil.rmtree(staged_root)
            if published:
                try:
                    self.repository.get(catalog_id)
                except KeyError:
                    if final_root.exists():
                        shutil.rmtree(final_root)
