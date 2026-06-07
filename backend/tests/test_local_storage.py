import pytest

from app.storage.local import InvalidObjectKeyError, LocalStorageProvider, ObjectNotFoundError


def test_local_storage_saves_reads_and_checks_existence(tmp_path) -> None:
    storage = LocalStorageProvider(root_path=tmp_path)
    content = b"<nfe>conteudo fiscal</nfe>"

    saved = storage.save_object(
        bucket="fiscal-documents",
        object_key="company-id/return-notes/note-id/nfe.xml",
        content_bytes=content,
        content_type="application/xml",
    )

    assert saved.size_bytes == len(content)
    assert storage.object_exists(bucket=saved.bucket, object_key=saved.object_key)
    assert storage.read_object(bucket=saved.bucket, object_key=saved.object_key) == content


@pytest.mark.parametrize(
    ("bucket", "object_key"),
    [
        ("", "company/file.xml"),
        ("../bucket", "company/file.xml"),
        ("fiscal-documents", "../file.xml"),
        ("fiscal-documents", "/absolute/file.xml"),
        ("fiscal-documents", "C:/absolute/file.xml"),
        ("fiscal-documents", "company\\file.xml"),
    ],
)
def test_local_storage_rejects_unsafe_paths(tmp_path, bucket: str, object_key: str) -> None:
    storage = LocalStorageProvider(root_path=tmp_path)

    with pytest.raises(InvalidObjectKeyError):
        storage.save_object(
            bucket=bucket,
            object_key=object_key,
            content_bytes=b"content",
            content_type="application/octet-stream",
        )


def test_local_storage_missing_object_raises_controlled_error(tmp_path) -> None:
    storage = LocalStorageProvider(root_path=tmp_path)

    with pytest.raises(ObjectNotFoundError):
        storage.read_object(bucket="fiscal-documents", object_key="company/missing.xml")
