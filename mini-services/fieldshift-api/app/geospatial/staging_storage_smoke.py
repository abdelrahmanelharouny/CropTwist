"""One-shot staging smoke test for the configured raster object store.

Runs from Railway's staging API pre-deploy command. It creates a temporary
organization and a tiny valid PNG object, verifies put/exists/read/stat/delete,
then removes both the object and organization. It never touches user-owned rows.
The payload is valid for both the PostgreSQL BYTEA and S3-compatible adapters.
"""
from __future__ import annotations

import base64
import hashlib
import uuid

from app.core.database import SessionLocal
from app.db.models import Organization
from app.geospatial.objectstore import get_raster_storage


def main() -> None:
    organization_id: uuid.UUID | None = None
    key: str | None = None
    storage = get_raster_storage()
    payload = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jNioAAAAASUVORK5CYII="
    )

    try:
        with SessionLocal() as session:
            organization = Organization(
                name=f"__staging_storage_smoke__{uuid.uuid4().hex[:12]}",
                organization_type="farm",
            )
            session.add(organization)
            session.commit()
            organization_id = organization.id

        key = (
            f"org/{organization_id}/field/{uuid.uuid4()}/"
            "source/staging-smoke/object.png"
        )
        stored = storage.put_bytes(
            key,
            payload,
            content_type="image/png",
        )
        assert stored.backend in {"postgres", "s3"}, stored.backend
        assert storage.exists(key), "object should exist after put"
        assert storage.read_bytes(key) == payload, "read-after-write mismatch"
        stat = storage.stat(key)
        assert stat.byte_size == len(payload), stat.byte_size
        if stat.checksum_sha256 is not None:
            assert stat.checksum_sha256 == hashlib.sha256(payload).hexdigest()

        storage.delete(key)
        assert not storage.exists(key), "object should be absent after delete"
        print(f"RASTER_OBJECTSTORE_SMOKE=PASS backend={stored.backend}")
    finally:
        if key:
            try:
                storage.delete(key)
            except Exception:
                pass
        if organization_id:
            with SessionLocal() as session:
                organization = session.get(Organization, organization_id)
                if organization is not None:
                    session.delete(organization)
                    session.commit()


if __name__ == "__main__":
    main()
