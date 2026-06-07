from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re


class StorageError(ValueError):
    pass


class InvalidObjectKeyError(StorageError):
    pass


class ObjectNotFoundError(StorageError):
    pass


@dataclass(frozen=True)
class StorageObject:
    bucket: str
    object_key: str
    content_type: str
    size_bytes: int


class LocalStorageProvider:
    def __init__(self, root_path: Path | str = ".local-storage") -> None:
        self.root_path = Path(root_path)

    def save_object(
        self,
        *,
        bucket: str,
        object_key: str,
        content_bytes: bytes,
        content_type: str,
    ) -> StorageObject:
        self._validate_content(content_bytes=content_bytes, content_type=content_type)
        path = self._safe_path(bucket=bucket, object_key=object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content_bytes)
        return StorageObject(
            bucket=bucket,
            object_key=object_key,
            content_type=content_type,
            size_bytes=len(content_bytes),
        )

    def read_object(self, *, bucket: str, object_key: str) -> bytes:
        path = self._safe_path(bucket=bucket, object_key=object_key)
        if not path.is_file():
            raise ObjectNotFoundError("Storage object not found")
        return path.read_bytes()

    def object_exists(self, *, bucket: str, object_key: str) -> bool:
        return self._safe_path(bucket=bucket, object_key=object_key).is_file()

    def _safe_path(self, *, bucket: str, object_key: str) -> Path:
        self._validate_bucket(bucket)
        self._validate_object_key(object_key)
        root = self.root_path.resolve()
        target = (root / bucket / Path(*PurePosixPath(object_key).parts)).resolve()
        if root != target and root not in target.parents:
            raise InvalidObjectKeyError("Invalid storage path")
        return target

    def _validate_bucket(self, bucket: str) -> None:
        if not bucket or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", bucket):
            raise InvalidObjectKeyError("Invalid storage bucket")

    def _validate_object_key(self, object_key: str) -> None:
        if not object_key or "\\" in object_key or re.match(r"^[A-Za-z]:", object_key):
            raise InvalidObjectKeyError("Invalid storage object key")
        path = PurePosixPath(object_key)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise InvalidObjectKeyError("Invalid storage object key")

    def _validate_content(self, *, content_bytes: bytes, content_type: str) -> None:
        if not content_bytes:
            raise StorageError("Storage content cannot be empty")
        if not content_type.strip():
            raise StorageError("Storage content type is required")
