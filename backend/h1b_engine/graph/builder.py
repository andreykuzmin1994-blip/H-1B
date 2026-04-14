"""Entity relationship graph construction + traversal."""
from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import and_, or_, select, text

from h1b_engine.db.base import get_session
from h1b_engine.db.models import Employer, EntityRelationship, SosEntity, Violation

log = logging.getLogger(__name__)


def _upsert_relationship(
    session,
    a: int,
    b: int,
    rel_type: str,
    confidence: float,
    evidence: dict[str, Any],
) -> bool:
    """Insert a relationship if absent. Always stores (min_id, max_id) for uniqueness."""
    if a == b:
        return False
    lo, hi = sorted([a, b])
    existing = session.execute(
        select(EntityRelationship.id).where(
            EntityRelationship.employer_id_a == lo,
            EntityRelationship.employer_id_b == hi,
            EntityRelationship.relationship_type == rel_type,
        )
    ).scalar_one_or_none()
    if existing:
        return False
    session.add(
        EntityRelationship(
            employer_id_a=lo,
            employer_id_b=hi,
            relationship_type=rel_type,
            confidence=confidence,
            evidence=evidence,
        )
    )
    return True


def build_address_links() -> int:
    """Link employers sharing (address_line1, city, state)."""
    added = 0
    with get_session() as session:
        rows = session.execute(
            select(Employer.id, Employer.address_line1, Employer.city, Employer.state).where(
                Employer.address_line1.is_not(None),
                Employer.city.is_not(None),
                Employer.state.is_not(None),
            )
        ).all()
        buckets: dict[tuple[str, str, str], list[int]] = defaultdict(list)
        for eid, line, city, state in rows:
            key = (line.upper().strip(), city.upper().strip(), state.upper().strip())
            buckets[key].append(eid)
        for key, ids in buckets.items():
            if len(ids) < 2:
                continue
            for a, b in combinations(ids, 2):
                if _upsert_relationship(
                    session,
                    a,
                    b,
                    "SHARED_ADDRESS",
                    confidence=0.6,
                    evidence={"address": " | ".join(key)},
                ):
                    added += 1
    log.info("build_address_links: %d new relationships", added)
    return added


def build_agent_links() -> int:
    """Link employers sharing an SOS registered agent."""
    added = 0
    with get_session() as session:
        rows = session.execute(
            select(SosEntity.employer_id, SosEntity.registered_agent, SosEntity.state).where(
                SosEntity.registered_agent.is_not(None),
                SosEntity.employer_id.is_not(None),
            )
        ).all()
        buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
        for eid, agent, state in rows:
            buckets[(agent.upper().strip(), (state or "").upper())].append(eid)
        for (agent, state), ids in buckets.items():
            if len(ids) < 2:
                continue
            for a, b in combinations(set(ids), 2):
                if _upsert_relationship(
                    session,
                    a,
                    b,
                    "SHARED_AGENT",
                    confidence=0.8,
                    evidence={"agent": agent, "state": state},
                ):
                    added += 1
    log.info("build_agent_links: %d new relationships", added)
    return added


def build_officer_links() -> int:
    """Link employers sharing at least one officer/director by exact name match."""
    added = 0
    with get_session() as session:
        rows = session.execute(
            select(SosEntity.employer_id, SosEntity.officers).where(
                SosEntity.officers.is_not(None),
                SosEntity.employer_id.is_not(None),
            )
        ).all()
        officer_to_ids: dict[str, set[int]] = defaultdict(set)
        for eid, officers in rows:
            if not officers:
                continue
            for off in officers:
                name = (off or {}).get("name")
                if not name:
                    continue
                officer_to_ids[name.upper().strip()].add(eid)
        for officer, ids in officer_to_ids.items():
            if len(ids) < 2:
                continue
            for a, b in combinations(ids, 2):
                if _upsert_relationship(
                    session,
                    a,
                    b,
                    "SHARED_OFFICER",
                    confidence=1.0,
                    evidence={"officer": officer},
                ):
                    added += 1
    log.info("build_officer_links: %d new relationships", added)
    return added


def build_name_variants(threshold: float = 85.0) -> int:
    """Fuzzy-match employer names within the same state using rapidfuzz token_sort_ratio."""
    added = 0
    with get_session() as session:
        rows = session.execute(
            select(Employer.id, Employer.name_normalized, Employer.state).where(
                Employer.name_normalized.is_not(None),
                Employer.state.is_not(None),
            )
        ).all()
        by_state: dict[str, list[tuple[int, str]]] = defaultdict(list)
        for eid, name, state in rows:
            by_state[state].append((eid, name))

        for state, entries in by_state.items():
            for (a_id, a_name), (b_id, b_name) in combinations(entries, 2):
                if not a_name or not b_name or a_name == b_name:
                    continue
                # Cheap prefix filter to avoid O(n^2) scoring blow-ups
                if abs(len(a_name) - len(b_name)) > max(len(a_name), len(b_name)) * 0.5:
                    continue
                score = fuzz.token_sort_ratio(a_name, b_name)
                if score >= threshold:
                    if _upsert_relationship(
                        session,
                        a_id,
                        b_id,
                        "NAME_VARIANT",
                        confidence=score / 100.0,
                        evidence={"score": score, "a": a_name, "b": b_name},
                    ):
                        added += 1
    log.info("build_name_variants: %d new relationships", added)
    return added


def build_all() -> dict[str, int]:
    return {
        "SHARED_ADDRESS": build_address_links(),
        "SHARED_AGENT": build_agent_links(),
        "SHARED_OFFICER": build_officer_links(),
        "NAME_VARIANT": build_name_variants(),
    }


# --------------------------------------------------------------------------- #
# Traversal
# --------------------------------------------------------------------------- #


SUBGRAPH_SQL_PG = text(
    """
    WITH RECURSIVE reachable(id, depth) AS (
        SELECT CAST(:start_id AS INTEGER), 0
      UNION
        SELECT CASE WHEN er.employer_id_a = r.id THEN er.employer_id_b ELSE er.employer_id_a END,
               r.depth + 1
          FROM entity_relationships er
          JOIN reachable r ON er.employer_id_a = r.id OR er.employer_id_b = r.id
         WHERE r.depth < :max_depth
    )
    SELECT DISTINCT id, depth FROM reachable
    """
)


def _traverse_in_python(session, employer_id: int, max_depth: int) -> list[tuple[int, int]]:
    """Portable BFS fallback when the database doesn't support recursive CTEs (SQLite)."""
    depth_map: dict[int, int] = {employer_id: 0}
    frontier = [employer_id]
    for depth in range(max_depth):
        if not frontier:
            break
        rows = session.execute(
            select(EntityRelationship).where(
                (EntityRelationship.employer_id_a.in_(frontier))
                | (EntityRelationship.employer_id_b.in_(frontier))
            )
        ).scalars().all()
        next_frontier: list[int] = []
        for rel in rows:
            for nid in (rel.employer_id_a, rel.employer_id_b):
                if nid not in depth_map:
                    depth_map[nid] = depth + 1
                    next_frontier.append(nid)
        frontier = next_frontier
    return list(depth_map.items())


def subgraph_for_employer(employer_id: int, max_depth: int = 2) -> dict[str, Any]:
    """Return a JSON-ready subgraph around ``employer_id`` up to ``max_depth`` hops."""
    with get_session() as session:
        dialect = session.bind.dialect.name if session.bind else ""
        if dialect == "postgresql":
            rows = session.execute(
                SUBGRAPH_SQL_PG, {"start_id": employer_id, "max_depth": max_depth}
            ).all()
            pairs = [(int(row[0]), int(row[1])) for row in rows]
        else:
            pairs = _traverse_in_python(session, employer_id, max_depth)

        node_ids = {p[0] for p in pairs}
        depth_map = {p[0]: p[1] for p in pairs}
        if not node_ids:
            return {"nodes": [], "edges": []}

        employers = session.execute(
            select(Employer).where(Employer.id.in_(node_ids))
        ).scalars().all()
        violators = {
            v[0]
            for v in session.execute(
                select(Violation.employer_id).where(Violation.employer_id.in_(node_ids))
            ).all()
        }

        edges = session.execute(
            select(EntityRelationship).where(
                and_(
                    EntityRelationship.employer_id_a.in_(node_ids),
                    EntityRelationship.employer_id_b.in_(node_ids),
                )
            )
        ).scalars().all()

    return {
        "nodes": [
            {
                "id": e.id,
                "name": e.name,
                "state": e.state,
                "anomaly_score": float(e.anomaly_score or 0),
                "is_violator": e.id in violators,
                "depth": depth_map.get(e.id, 0),
            }
            for e in employers
        ],
        "edges": [
            {
                "source": r.employer_id_a,
                "target": r.employer_id_b,
                "type": r.relationship_type,
                "confidence": float(r.confidence or 0),
                "evidence": r.evidence,
            }
            for r in edges
        ],
    }
