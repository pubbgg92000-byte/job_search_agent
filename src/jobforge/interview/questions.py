"""Practice question generation.

Two layers:

1. A deterministic bank keyed on topic + difficulty (no LLM). This guarantees
   tests are reproducible and that the engine still works offline.
2. An optional LLM augmentation layer (`llm_augment.generate_extra_questions`)
   that can add bespoke questions when the user wants more depth — every
   test mocks this away.

The bank is intentionally narrow (Node.js, TypeScript, PostgreSQL, system
design, behavioural) because Phase 3C's goal is to *help* the candidate
prep, not to be a question encyclopedia.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import asc, select

from jobforge.db.models import InterviewPlan, InterviewQuestion
from jobforge.db.session import session_scope
from jobforge.logging_setup import get_logger

log = get_logger("jobforge.interview.questions")

DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"
ALL_DIFFICULTIES = (DIFFICULTY_EASY, DIFFICULTY_MEDIUM, DIFFICULTY_HARD)

CATEGORY_TECHNICAL = "technical"
CATEGORY_SYSTEM_DESIGN = "system_design"
CATEGORY_BEHAVIORAL = "behavioral"


@dataclass(frozen=True)
class QuestionDTO:
    id: int | None
    plan_id: int
    category: str
    topic: str
    difficulty: str
    prompt: str
    answer_outline: str | None = None


# ---------------- bank ----------------


def _node_questions() -> list[QuestionDTO]:
    return [
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="node.js",
            difficulty=DIFFICULTY_EASY,
            prompt="Explain Node.js's event loop in two minutes. Why is it single-threaded?",
            answer_outline=(
                "libuv drives the loop; phases: timers → pending callbacks → poll → check → close. "
                "Single-threaded JS, but I/O via libuv thread pool."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="node.js",
            difficulty=DIFFICULTY_MEDIUM,
            prompt="A Node service is dropping requests under load. Walk me through how you'd debug.",
            answer_outline=(
                "Check event loop lag, GC pauses, blocking sync calls, downstream timeouts; "
                "profile with clinic.js, inspect with --inspect; check fd limits."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="node.js",
            difficulty=DIFFICULTY_HARD,
            prompt="Design a streaming JSON parser in Node for files larger than memory.",
            answer_outline=(
                "Readable stream, push-parser (oboe / clarinet style), backpressure, "
                "chunk boundaries, encoding edge cases, error propagation."
            ),
        ),
    ]


def _typescript_questions() -> list[QuestionDTO]:
    return [
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="typescript",
            difficulty=DIFFICULTY_EASY,
            prompt="What's the difference between `interface` and `type` in TypeScript?",
            answer_outline=(
                "Both describe object shapes; type can alias unions/primitives, interface "
                "supports declaration merging; class implements either."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="typescript",
            difficulty=DIFFICULTY_MEDIUM,
            prompt="Implement a `DeepReadonly<T>` utility type and describe the tradeoffs.",
            answer_outline=(
                "Recursive mapped type with conditional check for object vs primitive; "
                "edge cases: arrays, functions, branded types."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="typescript",
            difficulty=DIFFICULTY_HARD,
            prompt="Walk me through narrowing in TypeScript and the corner cases where it fails.",
            answer_outline=(
                "Discriminated unions, type predicates, assertion functions; aliasing kills "
                "narrowing, captured closures can revert types; explain `never` exhaustiveness."
            ),
        ),
    ]


def _postgres_questions() -> list[QuestionDTO]:
    return [
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="postgresql",
            difficulty=DIFFICULTY_EASY,
            prompt="When would you choose a B-tree index over a GIN index?",
            answer_outline=(
                "B-tree for equality/range; GIN for composite types (jsonb, array, fts); "
                "size/write-amplification tradeoffs."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="postgresql",
            difficulty=DIFFICULTY_MEDIUM,
            prompt="Explain MVCC and how Postgres handles concurrent writes.",
            answer_outline=(
                "Tuple versions, xmin/xmax, snapshot isolation; vacuum reclaims; "
                "row-level locks; serializable vs repeatable read tradeoffs."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_TECHNICAL, topic="postgresql",
            difficulty=DIFFICULTY_HARD,
            prompt="Design a deadlock-free schema and write path for a 'reserve seats' booking flow.",
            answer_outline=(
                "Consistent lock ordering, SELECT FOR UPDATE SKIP LOCKED, advisory locks, "
                "idempotent retries; consider partitioned counters to reduce contention."
            ),
        ),
    ]


def _system_design_questions() -> list[QuestionDTO]:
    return [
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_SYSTEM_DESIGN, topic="system design",
            difficulty=DIFFICULTY_EASY,
            prompt="Design a URL shortener for ~10k QPS reads.",
            answer_outline=(
                "Base62 ids, KV store for redirects, edge cache for hot keys, "
                "rate-limit writes, plan for analytics async."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_SYSTEM_DESIGN, topic="system design",
            difficulty=DIFFICULTY_MEDIUM,
            prompt="Design the feed-write fan-out for a Twitter-like app at 1M users.",
            answer_outline=(
                "Push vs pull vs hybrid; celeb fan-out problem; write buffer; "
                "user cache; cold timeline generation."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_SYSTEM_DESIGN, topic="system design",
            difficulty=DIFFICULTY_HARD,
            prompt="Design a globally-replicated leader-election system. What CAP tradeoffs do you accept?",
            answer_outline=(
                "Raft / Paxos quorum, regional placement, lease times, split-brain "
                "mitigation; CP — sacrifice availability during partition for consistency."
            ),
        ),
    ]


def _behavioral_questions() -> list[QuestionDTO]:
    return [
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_BEHAVIORAL, topic="behavioral",
            difficulty=DIFFICULTY_EASY,
            prompt="Tell me about a time you delivered feedback that was hard to hear.",
            answer_outline=(
                "STAR: situation, the specific feedback, framing for receiver, follow-through; "
                "lesson learned about preparing context."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_BEHAVIORAL, topic="behavioral",
            difficulty=DIFFICULTY_MEDIUM,
            prompt="Describe a production incident you led end-to-end.",
            answer_outline=(
                "STAR: detection, triage, mitigation, RCA, follow-up actions; "
                "highlight ownership and the post-mortem cultural takeaway."
            ),
        ),
        QuestionDTO(
            id=None, plan_id=0, category=CATEGORY_BEHAVIORAL, topic="behavioral",
            difficulty=DIFFICULTY_HARD,
            prompt="Tell me about a multi-quarter project where the strategy had to pivot.",
            answer_outline=(
                "STAR with explicit decision criteria, stakeholder alignment, sunk-cost "
                "reasoning, communication to the team, measurable outcome."
            ),
        ),
    ]


_TOPIC_LIBRARY = {
    "node.js": _node_questions,
    "typescript": _typescript_questions,
    "postgresql": _postgres_questions,
    "system design": _system_design_questions,
    "behavioral": _behavioral_questions,
}


def topics_for_plan(*, technical_topics: list[str]) -> list[str]:
    """Map free-form plan topics → bank keys, in priority order.

    Always include the four canonical technical topics + behavioural, in
    the order: missing-skill matches first, then the rest.
    """
    canonical_order = ["node.js", "typescript", "postgresql", "system design"]
    priority = [t.lower() for t in technical_topics]
    ordered: list[str] = []
    for p in priority:
        if p in _TOPIC_LIBRARY and p != "behavioral" and p not in ordered:
            ordered.append(p)
    for c in canonical_order:
        if c not in ordered:
            ordered.append(c)
    ordered.append("behavioral")
    return ordered


def generate_question_bank(*, technical_topics: list[str]) -> list[QuestionDTO]:
    """Build the deterministic question bank for a plan.

    Categorized into easy/medium/hard for every topic.
    """
    bank: list[QuestionDTO] = []
    for topic in topics_for_plan(technical_topics=technical_topics):
        for q in _TOPIC_LIBRARY[topic]():
            bank.append(q)
    return bank


# ---------------- persistence ----------------


async def _assert_plan_exists(plan_id: int) -> None:
    async with session_scope() as session:
        row = await session.get(InterviewPlan, plan_id)
        if row is None:
            from jobforge.applications import ApplicationError

            raise ApplicationError(f"interview plan {plan_id} not found")


async def generate_questions(
    plan_id: int,
    *,
    technical_topics: list[str],
    persist: bool = True,
) -> list[QuestionDTO]:
    await _assert_plan_exists(plan_id)
    bank = generate_question_bank(technical_topics=technical_topics)
    bank = [
        QuestionDTO(
            id=None,
            plan_id=plan_id,
            category=q.category,
            topic=q.topic,
            difficulty=q.difficulty,
            prompt=q.prompt,
            answer_outline=q.answer_outline,
        )
        for q in bank
    ]
    if not persist:
        return bank

    persisted: list[QuestionDTO] = []
    async with session_scope() as session:
        for q in bank:
            row = InterviewQuestion(
                plan_id=plan_id,
                category=q.category,
                topic=q.topic,
                difficulty=q.difficulty,
                prompt=q.prompt,
                answer_outline=q.answer_outline,
            )
            session.add(row)
            await session.flush()
            await session.refresh(row)
            persisted.append(
                QuestionDTO(
                    id=row.id,
                    plan_id=row.plan_id,
                    category=row.category,
                    topic=row.topic,
                    difficulty=row.difficulty,
                    prompt=row.prompt,
                    answer_outline=row.answer_outline,
                )
            )
            session.expunge(row)

    log.info(
        "interview.questions.generated",
        extra={"plan_id": plan_id, "count": len(persisted)},
    )
    return persisted


async def list_questions(
    plan_id: int,
    *,
    category: str | None = None,
    difficulty: str | None = None,
) -> list[QuestionDTO]:
    async with session_scope() as session:
        stmt = select(InterviewQuestion).where(InterviewQuestion.plan_id == plan_id)
        if category:
            stmt = stmt.where(InterviewQuestion.category == category)
        if difficulty:
            stmt = stmt.where(InterviewQuestion.difficulty == difficulty)
        stmt = stmt.order_by(
            asc(InterviewQuestion.category),
            asc(InterviewQuestion.difficulty),
            asc(InterviewQuestion.id),
        )
        rows = (await session.execute(stmt)).scalars().all()
        for r in rows:
            session.expunge(r)
    return [
        QuestionDTO(
            id=r.id,
            plan_id=r.plan_id,
            category=r.category,
            topic=r.topic,
            difficulty=r.difficulty,
            prompt=r.prompt,
            answer_outline=r.answer_outline,
        )
        for r in rows
    ]


def question_to_dict(q: QuestionDTO) -> dict[str, Any]:
    return {
        "id": q.id,
        "plan_id": q.plan_id,
        "category": q.category,
        "topic": q.topic,
        "difficulty": q.difficulty,
        "prompt": q.prompt,
        "answer_outline": q.answer_outline,
    }
