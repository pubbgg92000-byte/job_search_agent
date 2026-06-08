"""Recruiter contact service — discovery + CRUD."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from jobforge.db.models import RecruiterContact
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger
from jobforge.outreach.providers import (
    ContactDiscoveryProvider,
    DiscoveredContact,
    ManualProvider,
)

log = get_logger("jobforge.outreach.contacts")


class OutreachError(Exception):
    """Service-level error."""


VALID_KINDS = frozenset({"recruiter", "talent_partner", "hiring_manager", "engineer"})


def _norm_name(name: str) -> str:
    """Identity normalization — case-insensitive, trimmed, single-spaced."""
    return " ".join(str(name).split()).lower()


@dataclass
class UpsertContactRequest:
    company: str
    name: str
    kind: str = "recruiter"
    role: str | None = None
    linkedin_url: str | None = None
    email: str | None = None
    phone: str | None = None
    source: str = "manual"
    confidence: int = 75
    notes: str | None = None


def _validate(req: UpsertContactRequest) -> None:
    if not (req.company or "").strip():
        raise OutreachError("company is required")
    if not (req.name or "").strip():
        raise OutreachError("name is required")
    if req.kind not in VALID_KINDS:
        raise OutreachError(f"invalid kind '{req.kind}' (allowed: {sorted(VALID_KINDS)})")
    if not (0 <= req.confidence <= 100):
        raise OutreachError("confidence must be 0-100")


async def upsert_contact(user_id: int, req: UpsertContactRequest) -> RecruiterContact:
    _validate(req)
    norm = _norm_name(req.name)
    async with session_scope() as session:
        existing = (
            await session.execute(
                select(RecruiterContact)
                .where(RecruiterContact.user_id == user_id)
                .where(RecruiterContact.company == req.company)
            )
        ).scalars().all()
        match = next((c for c in existing if _norm_name(c.name) == norm), None)
        if match is None:
            match = RecruiterContact(
                user_id=user_id,
                company=req.company,
                name=req.name.strip(),
                kind=req.kind,
                role=req.role,
                linkedin_url=req.linkedin_url,
                email=req.email,
                phone=req.phone,
                source=req.source,
                confidence=req.confidence,
                notes=req.notes,
            )
            session.add(match)
        else:
            # Update non-null fields. Confidence widens — never drops on
            # re-discovery, so a one-off low-confidence hint won't overwrite
            # a previously high-confidence manual entry.
            if req.role:
                match.role = req.role
            if req.linkedin_url:
                match.linkedin_url = req.linkedin_url
            if req.email:
                match.email = req.email
            if req.phone:
                match.phone = req.phone
            if req.kind:
                match.kind = req.kind
            if req.notes:
                match.notes = req.notes
            if req.source and req.source != match.source and match.source == "manual":
                # Prefer the more specific source over `manual` for traceability.
                match.source = req.source
            match.confidence = max(match.confidence, req.confidence)
        try:
            await session.flush()
        except IntegrityError as exc:  # pragma: no cover - defensive
            await session.rollback()
            raise OutreachError("duplicate contact") from exc
        await session.refresh(match)
        session.expunge(match)
        log.info(
            "outreach.contact.upserted",
            extra={
                "contact_id": match.id,
                "company": match.company,
                "kind": match.kind,
                "source": match.source,
            },
        )
        return match


async def list_contacts(
    user_id: int,
    *,
    company: str | None = None,
    kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[RecruiterContact]]:
    async with session_scope() as session:
        filters = [RecruiterContact.user_id == user_id]
        if company:
            filters.append(RecruiterContact.company == company)
        if kind:
            filters.append(RecruiterContact.kind == kind)
        from sqlalchemy import func as sa_func
        total = int(
            (
                await session.execute(
                    select(sa_func.count(RecruiterContact.id)).where(*filters)
                )
            ).scalar_one()
        )
        rows = (
            await session.execute(
                select(RecruiterContact)
                .where(*filters)
                .order_by(desc(RecruiterContact.last_updated_at))
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        for r in rows:
            session.expunge(r)
    return total, list(rows)


async def get_contact(user_id: int, contact_id: int) -> RecruiterContact | None:
    async with session_scope() as session:
        row = await session.get(RecruiterContact, contact_id)
        if row is None or row.user_id != user_id:
            return None
        session.expunge(row)
        return row


async def delete_contact(user_id: int, contact_id: int) -> bool:
    async with session_scope() as session:
        row = await session.get(RecruiterContact, contact_id)
        if row is None or row.user_id != user_id:
            return False
        await session.delete(row)
    return True


async def discover_contacts(
    user_id: int,
    company: str,
    *,
    providers: list[ContactDiscoveryProvider] | None = None,
    hints: dict[str, Any] | None = None,
    persist: bool = True,
) -> list[RecruiterContact]:
    """Run every provider, dedupe by normalized name, upsert.

    Returns the resulting (possibly merged) contact rows. Safe to call
    repeatedly — same company + same name maps to the same row.
    """
    if not (company or "").strip():
        raise OutreachError("company is required")
    provider_list: list[ContactDiscoveryProvider] = list(providers or [ManualProvider()])

    collected: dict[str, DiscoveredContact] = {}
    for provider in provider_list:
        try:
            items = await provider.discover(company, hints=hints)
        except Exception as exc:
            log.warning(
                "outreach.discovery.provider_error",
                extra={"provider": provider.name, "error": type(exc).__name__},
            )
            continue
        for item in items:
            key = _norm_name(item.name)
            if not key:
                continue
            cur = collected.get(key)
            if cur is None or item.confidence > cur.confidence:
                collected[key] = item

    if not persist:
        # Return a transient view — never bypass the unique constraint.
        return [
            RecruiterContact(
                user_id=user_id,
                company=company,
                name=c.name,
                kind=c.kind,
                role=c.role,
                linkedin_url=c.linkedin_url,
                email=c.email,
                phone=c.phone,
                source=c.source,
                confidence=c.confidence,
                notes=c.notes,
            )
            for c in collected.values()
        ]

    out: list[RecruiterContact] = []
    for c in collected.values():
        row = await upsert_contact(
            user_id,
            UpsertContactRequest(
                company=company,
                name=c.name,
                kind=c.kind,
                role=c.role,
                linkedin_url=c.linkedin_url,
                email=c.email,
                phone=c.phone,
                source=c.source,
                confidence=c.confidence,
                notes=c.notes,
            ),
        )
        out.append(row)
    log.info(
        "outreach.discovery.complete",
        extra={"company": company, "found": len(out)},
    )
    return out


def contact_to_dict(c: RecruiterContact) -> dict[str, Any]:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "company": c.company,
        "name": c.name,
        "kind": c.kind,
        "role": c.role,
        "linkedin_url": c.linkedin_url,
        "email": c.email,
        "phone": c.phone,
        "source": c.source,
        "confidence": c.confidence,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "last_updated_at": c.last_updated_at.isoformat() if c.last_updated_at else None,
    }
