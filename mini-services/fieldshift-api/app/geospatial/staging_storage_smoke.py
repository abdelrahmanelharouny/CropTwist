"""One-shot staging smoke test for the bounded PostgreSQL raster object store.

Runs from Railway's staging API pre-deploy command. It creates a temporary
organization and one tiny object, verifies put/exists/read/stat/delete, then
removes both the object and organization. It never touches user-owned rows.
"""
from __future__ import annotations

import uuid

from app.core.database import SessionLocal
from app.db.models import Organization
from app.geospatial.objectstore import get_raster_storage


def main() -> None:
    organization_id: uuid.UUID | None = None
    key: str | None = None
    storage = get_raster_storage()
    payload = b"croptwist-staging-postgres-objectstore-smoke-v1"

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
            "source/staging-smoke/object.bin"
        )
        stored = storage.put_bytes(
            key,
            payload,
            content_type="application/octet-stream",
        )
        assert stored.backend == "postgres", stored.backend
        assert storage.exists(key), "object should exist after put"
        assert storage.read_bytes(key) == payload, "read-after-write mismatch"
        stat = storage.stat(key)
        assert stat.byte_size == len(payload), stat.byte_size
        assert stat.checksum_sha256 is not None, "checksum missing"

        storage.delete(key)
        assert not storage.exists(key), "object should be absent after delete"
        print("POSTGRES_RASTER_OBJECTSTORE_SMOKE=PASS")
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
