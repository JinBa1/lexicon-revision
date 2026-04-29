from src.storage.base import (
    InvalidKeyError,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageAuthError,
    ObjectStorageConfigError,
    ObjectStorageError,
    PresignedUrl,
    StoredObject,
)
from src.storage.config import (
    LocalStorageConfig,
    ObjectStorageSettings,
    S3StorageConfig,
    build_object_storage,
    load_object_storage_settings,
)
from src.storage.conversion import (
    ConvertedPaperArtifacts,
    discover_converted_paper_artifacts,
    load_local_manifests,
    local_manifest_path,
    upload_converted_paper_artifacts,
)
from src.storage.keys import (
    conversion_run_id_from_stem,
    mineru_artifact_key,
    sha256_blob_key,
    validate_key,
)
from src.storage.local import LocalObjectStorage, validate_local_presigned_url
from src.storage.manifest import ArtifactManifest, ManifestArtifact

__all__ = [
    "ArtifactManifest",
    "InvalidKeyError",
    "LocalStorageConfig",
    "LocalObjectStorage",
    "ManifestArtifact",
    "ObjectNotFoundError",
    "ObjectStorage",
    "ObjectStorageAuthError",
    "ObjectStorageConfigError",
    "ObjectStorageError",
    "ObjectStorageSettings",
    "PresignedUrl",
    "S3ObjectStorage",
    "S3StorageConfig",
    "StoredObject",
    "ConvertedPaperArtifacts",
    "conversion_run_id_from_stem",
    "discover_converted_paper_artifacts",
    "build_object_storage",
    "load_local_manifests",
    "load_object_storage_settings",
    "local_manifest_path",
    "mineru_artifact_key",
    "sha256_blob_key",
    "upload_converted_paper_artifacts",
    "validate_key",
    "validate_local_presigned_url",
]


def __getattr__(name: str):
    if name == "S3ObjectStorage":
        try:
            from src.storage.s3 import S3ObjectStorage as _S3ObjectStorage
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dep guard
            raise ImportError(
                "S3ObjectStorage requires the optional botocore dependency"
            ) from exc

        return _S3ObjectStorage
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
