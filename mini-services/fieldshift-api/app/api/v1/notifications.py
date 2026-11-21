"""Notification center endpoints (P3 W5.3).

Wraps `app/notifications/service.py`. Notification rows are org-scoped or
user-addressed; the visible set = org rows + rows addressed to the caller
(scope logic lives in the service). Routes accept an optional
`organization_id` query parameter for multi-org users; it defaults to the
caller's OLDEST active organization (same deterministic convention the
farms domain uses).

Severity and category filters are applied in the service's SQL query so
pagination and aggregate counts use one consistent, tenant-scoped result set.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import Forbidden, ValidationFailed
from app.domains.identity.service import get_principal
from app.notifications import service as notifications_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


# --------------------------------------------------------------- helpers
def _resolve_org_id(principal: Any, organization_id: uuid.UUID | None) -> uuid.UUID:
    if organization_id is not None:
        return organization_id  # the service enforces membership
    active = [m for m in principal.memberships if m.status == "active"]
    if not active:
        raise Forbidden("You do not belong to an active organization.")
    active.sort(key=lambda m: (m.created_at or datetime.now(UTC), m.organization_id))
    return active[0].organization_id


def _validate_category(category: str | None) -> str | None:
    if category is not None and category not in notifications_service.CATEGORIES:
        raise ValidationFailed(
            f"Unknown notification category '{category}'. "
            f"Valid categories: {', '.join(notifications_service.CATEGORIES)}."
        )
    return category


def _validate_severity(severity: str | None) -> str | None:
    if severity is not None and severity not in notifications_service.SEVERITIES:
        raise ValidationFailed(
            f"Unknown notification severity '{severity}'. "
            f"Valid severities: {', '.join(notifications_service.SEVERITIES)}."
        )
    return severity



# ------------------------------------------------------------ request models
class NotificationReadPatch(BaseModel):
    read: bool = True


class NotificationPreferenceUpdate(BaseModel):
    category: str
    in_app_enabled: bool | None = None
    email_enabled: bool | None = None


# ------------------------------------------------------------------- routes
@router.get("")
def list_notifications(
    unread_only: bool = False,
    severity: str | None = None,
    category: str | None = None,
    type_: str | None = Query(default=None, alias="type"),
    organization_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    principal: Any = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Notifications visible to the caller (org rows + user-addressed rows),
    newest first. Filters: unread_only, severity, category (also accepted as
    `type`); pagination via limit/offset."""
    org_id = _resolve_org_id(principal, organization_id)
    severity = _validate_severity(severity)
    category = _validate_category(category or type_)
    rows, total, unread = notifications_service.list_notifications(
        db,
        principal,
        organization_id=org_id,
        unread_only=unread_only,
        category=category,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [notifications_service.notification_payload(n) for n in rows],
        "total": total,
        "unread": unread,
        "limit": limit,
        "offset": offset,
        "organization_id": str(org_id),
    }


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: uuid.UUID,
    payload: NotificationReadPatch | None = None,
    organization_id: uuid.UUID | None = None,
    principal: Any = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    org_id = _resolve_org_id(principal, organization_id)
    read = payload.read if payload else True
    notification = notifications_service.mark_read(
        db,
        principal,
        organization_id=org_id,
        notification_id=notification_id,
        read=read,
    )
    return notifications_service.notification_payload(notification)


@router.post("/read-all")
def mark_all_notifications_read(
    organization_id: uuid.UUID | None = None,
    principal: Any = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    org_id = _resolve_org_id(principal, organization_id)
    marked = notifications_service.mark_all_read(
        db, principal, organization_id=org_id
    )
    return {"marked": marked, "organization_id": str(org_id)}


@router.get("/unread-count")
def unread_count(
    organization_id: uuid.UUID | None = None,
    principal: Any = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    org_id = _resolve_org_id(principal, organization_id)
    _rows, _total, unread = notifications_service.list_notifications(
        db, principal, organization_id=org_id, limit=1
    )
    return {"unread": unread, "organization_id": str(org_id)}


@router.get("/preferences")
def get_notification_preferences(
    principal: Any = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Per-category delivery preferences (full 8-category list, defaults
    in_app=True / email=False)."""
    rows = notifications_service.get_preferences(db, principal.id)
    return {
        "items": [
            {
                "category": r.category,
                "in_app_enabled": r.in_app_enabled,
                "email_enabled": r.email_enabled,
            }
            for r in rows
        ]
    }


@router.put("/preferences")
def put_notification_preferences(
    payload: NotificationPreferenceUpdate,
    principal: Any = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Upsert one category's delivery preferences. The category is validated
    here (the service raises ValueError for unknown categories)."""
    _validate_category(payload.category)
    pref = notifications_service.set_preference(
        db,
        principal.id,
        category=payload.category,
        in_app_enabled=payload.in_app_enabled,
        email_enabled=payload.email_enabled,
    )
    return {
        "category": pref.category,
        "in_app_enabled": pref.in_app_enabled,
        "email_enabled": pref.email_enabled,
    }
