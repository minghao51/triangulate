"""Case writer admission and fencing (R02).

One transactional owner token per case. A long-lived writer (an investigation
run or a case-bound intake item) claims it atomically before any case-bound
write and validates it in every case-bound write transaction, including after
awaited external work. Short writers (review, exception, annotation) claim,
write, validate and release inside a single transaction.

An explicit CLI interrupt atomically invalidates the token and marks the owning
invocation interrupted. A superseded writer's later commit then fails closed.
There is no elapsed-time recovery and no GET-side recovery.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterator, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from src.storage.models import TopicCase

OWNER_KIND_RUN = "run"
OWNER_KIND_INTAKE = "intake"
OWNER_KIND_REVIEW = "review"
OWNER_KIND_EXCEPTION = "exception"
OWNER_KIND_ANNOTATION = "annotation"
OWNER_KIND_EVALUATION = "evaluation"
OWNER_KIND_EVIDENCE = "evidence"

OWNER_KINDS = frozenset(
    {
        OWNER_KIND_RUN,
        OWNER_KIND_INTAKE,
        OWNER_KIND_REVIEW,
        OWNER_KIND_EXCEPTION,
        OWNER_KIND_ANNOTATION,
        OWNER_KIND_EVALUATION,
        OWNER_KIND_EVIDENCE,
    }
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CaseWriterConflict(RuntimeError):
    """A case is owned by another writer, or this writer's token was superseded.

    ``active_kind``/``active_ref_id`` are diagnostics for the caller and the CLI;
    they never carry the active token. The message is safe to show to an operator
    and never includes the token itself.
    """

    def __init__(
        self,
        case_id: str,
        *,
        operation: str | None = None,
        active_kind: str | None = None,
        active_ref_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.case_id = case_id
        self.operation = operation
        self.active_kind = active_kind
        self.active_ref_id = active_ref_id
        self.reason = reason
        if reason:
            message = f"Case {case_id}: {reason}"
        elif active_kind:
            reference = f" ({active_ref_id})" if active_ref_id else ""
            message = (
                f"Case {case_id} is currently owned by a {active_kind} writer"
                f"{reference}; another case-bound write was rejected."
            )
        else:
            message = f"Case {case_id} has no available writer ownership."
        super().__init__(message)


@dataclass(frozen=True)
class CaseOwner:
    """Current owner snapshot; ``token`` is None when the case is unowned."""

    case_id: str
    token: str | None
    kind: str | None
    ref_id: str | None
    claimed_at: datetime | None

    @property
    def is_owned(self) -> bool:
        return self.token is not None

    @property
    def summary(self) -> dict[str, str | None]:
        """Owner diagnostics without the token."""
        return {
            "caseId": self.case_id,
            "kind": self.kind,
            "refId": self.ref_id,
            "claimedAt": self.claimed_at.isoformat() if self.claimed_at else None,
        }


def new_writer_token() -> str:
    """Return a fresh opaque owner token."""
    return uuid.uuid4().hex


def read_case_owner(session: Session, case_id: str) -> CaseOwner:
    """Read the current committed owner fields (no token values are logged)."""
    row = session.execute(
        select(
            TopicCase.id,
            TopicCase.owner_token,
            TopicCase.owner_kind,
            TopicCase.owner_ref_id,
            TopicCase.owner_claimed_at,
        ).where(TopicCase.id == case_id)
    ).first()
    if row is None:
        raise CaseWriterConflict(case_id, reason="case not found")
    return CaseOwner(
        case_id=row[0],
        token=row[1],
        kind=row[2],
        ref_id=row[3],
        claimed_at=row[4],
    )


def claim_case_ownership(
    session: Session,
    case_id: str,
    *,
    token: str,
    kind: str,
    ref_id: str | None = None,
) -> None:
    """Atomically claim an unowned case; raise :class:`CaseWriterConflict`.

    The conditional ``UPDATE ... WHERE owner_token IS NULL`` is the admission
    decision, so two writers cannot both believe they own the case. The caller
    owns the transaction: this never commits or rolls back.
    """
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(TopicCase)
            .where(TopicCase.id == case_id, TopicCase.owner_token.is_(None))
            .values(
                owner_token=token,
                owner_kind=kind,
                owner_ref_id=ref_id,
                owner_claimed_at=_utcnow(),
            )
            .execution_options(synchronize_session=False)
        ),
    )
    if result.rowcount != 1:
        owner = read_case_owner(session, case_id)
        raise CaseWriterConflict(
            case_id,
            operation=kind,
            active_kind=owner.kind,
            active_ref_id=owner.ref_id,
        )


def validate_case_ownership(
    session: Session,
    case_id: str,
    token: str | None,
    *,
    operation: str | None = None,
) -> None:
    """Fail closed unless ``token`` is the currently committed owner.

    Must run inside the writer's write transaction immediately before commit so
    an interrupt or takeover after an await cannot be missed.
    """
    owner = read_case_owner(session, case_id)
    if token is None or owner.token != token:
        raise CaseWriterConflict(
            case_id,
            operation=operation,
            active_kind=owner.kind,
            active_ref_id=owner.ref_id,
        )


def validate_or_allow_legacy_writer(
    session: Session,
    case_id: str,
    token: str | None,
    *,
    operation: str | None = None,
) -> None:
    """Validate when the case has an active owner; allow an unowned legacy write.

    Used only by direct ``store_event_in_db`` callers that predate the guard: a
    write while a guarded writer owns the case is rejected, while the historical
    unowned single-writer path remains compatible. Known external direct-SQL
    scripts are not protected by this application-level check.
    """
    owner = read_case_owner(session, case_id)
    if not owner.is_owned:
        if token is None:
            # Historical unowned single-writer path.
            return
        # A supplied token must still be the active owner: a superseded writer
        # cannot fall back to the legacy path after an interrupt.
        raise CaseWriterConflict(
            case_id,
            operation=operation,
            reason="supplied owner token is not the active owner",
        )
    if token is None or owner.token != token:
        raise CaseWriterConflict(
            case_id,
            operation=operation,
            active_kind=owner.kind,
            active_ref_id=owner.ref_id,
        )


def release_case_ownership(session: Session, case_id: str, token: str | None) -> bool:
    """Clear ownership only if ``token`` still owns the case.

    Returns False when the token was already superseded (for example by an
    interrupt); this is not an error, but a superseded writer may not commit
    case-bound data afterwards.
    """
    if not token:
        return False
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(TopicCase)
            .where(TopicCase.id == case_id, TopicCase.owner_token == token)
            .values(
                owner_token=None,
                owner_kind=None,
                owner_ref_id=None,
                owner_claimed_at=None,
            )
            .execution_options(synchronize_session=False)
        ),
    )
    return result.rowcount == 1


def invalidate_case_ownership(
    session: Session,
    case_id: str,
    *,
    expected_token: str | None = None,
    expected_ref_id: str | None = None,
) -> CaseOwner:
    """Atomically invalidate the active owner after matching the expected identity.

    Used by the explicit CLI interrupt. The caller records the interrupted run
    state in the same transaction. Raises :class:`CaseWriterConflict` when there
    is no active owner or the supplied token/ref does not match.
    """
    owner = read_case_owner(session, case_id)
    if not owner.is_owned:
        raise CaseWriterConflict(case_id, reason="no active writer to interrupt")
    if expected_token is not None and owner.token != expected_token:
        raise CaseWriterConflict(
            case_id,
            operation="interrupt",
            reason="supplied owner token does not match the active writer",
        )
    if expected_ref_id is not None and owner.ref_id != expected_ref_id:
        raise CaseWriterConflict(
            case_id,
            operation="interrupt",
            reason="supplied run/owner reference does not match the active writer",
            active_kind=owner.kind,
            active_ref_id=owner.ref_id,
        )
    result = cast(
        "CursorResult[Any]",
        session.execute(
            update(TopicCase)
            .where(TopicCase.id == case_id, TopicCase.owner_token == owner.token)
            .values(
                owner_token=None,
                owner_kind=None,
                owner_ref_id=None,
                owner_claimed_at=None,
            )
            .execution_options(synchronize_session=False)
        ),
    )
    if result.rowcount != 1:
        raise CaseWriterConflict(
            case_id,
            operation="interrupt",
            reason="ownership changed while the interrupt was being applied",
        )
    return owner


@contextmanager
def case_write_admission(
    session: Session,
    case_id: str,
    *,
    kind: str,
    ref_id: str | None = None,
) -> Iterator[str]:
    """Claim, validate and release inside one caller-owned transaction.

    Intended for short case-bound writers: the claim, the writes, the validation
    and the release are committed atomically by the caller, so a crash cannot
    leak ownership and an active long-lived writer is rejected at admission.
    The caller must commit after the context exits normally and must not commit
    after an exception.
    """
    token = new_writer_token()
    claim_case_ownership(session, case_id, token=token, kind=kind, ref_id=ref_id)
    try:
        yield token
    except Exception:
        # The caller's transaction must roll back; do not release here so a
        # caller that ignores the exception can never commit a case-bound write
        # with silently cleared ownership.
        raise
    else:
        validate_case_ownership(session, case_id, token, operation=kind)
        release_case_ownership(session, case_id, token)


__all__ = [
    "CaseOwner",
    "CaseWriterConflict",
    "OWNER_KINDS",
    "OWNER_KIND_ANNOTATION",
    "OWNER_KIND_EVALUATION",
    "OWNER_KIND_EVIDENCE",
    "OWNER_KIND_EXCEPTION",
    "OWNER_KIND_INTAKE",
    "OWNER_KIND_REVIEW",
    "OWNER_KIND_RUN",
    "case_write_admission",
    "claim_case_ownership",
    "invalidate_case_ownership",
    "new_writer_token",
    "read_case_owner",
    "release_case_ownership",
    "validate_case_ownership",
    "validate_or_allow_legacy_writer",
]
