"""Tests for the entity graph builder (without recursive CTE - that needs PG)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from h1b_engine.db.models import Employer, EntityRelationship, SosEntity
from h1b_engine.graph.builder import (
    build_address_links,
    build_agent_links,
    build_name_variants,
    build_officer_links,
)


@pytest.fixture
def three_employers(session_factory):
    s = session_factory()
    # Use names that differ only in suffix wording so the fuzz matcher fires.
    a = Employer(name="Bright Star Consulting", name_normalized="BRIGHT STAR",
                 state="FL", address_line1="1 Palm Way", city="Miami", zip="33101")
    b = Employer(name="Brightstar Consultants", name_normalized="BRIGHTSTAR",
                 state="FL", address_line1="1 Palm Way", city="Miami", zip="33101")
    c = Employer(name="Unrelated Co", name_normalized="UNRELATED",
                 state="FL", address_line1="99 Other Rd", city="Orlando", zip="32801")
    s.add_all([a, b, c])
    s.commit()
    return s, a, b, c


def test_address_links_created(session_factory, three_employers):
    s, a, b, c = three_employers
    n = build_address_links()
    assert n == 1
    rels = s.execute(select(EntityRelationship)).scalars().all()
    assert len(rels) == 1
    rel = rels[0]
    assert rel.relationship_type == "SHARED_ADDRESS"
    assert {rel.employer_id_a, rel.employer_id_b} == {a.id, b.id}


def test_name_variant_detection(session_factory, three_employers):
    s, a, b, c = three_employers
    n = build_name_variants(threshold=80)
    assert n >= 1
    rels = s.execute(
        select(EntityRelationship).where(EntityRelationship.relationship_type == "NAME_VARIANT")
    ).scalars().all()
    pair = {rels[0].employer_id_a, rels[0].employer_id_b}
    assert pair == {a.id, b.id}


def test_agent_and_officer_links(session_factory, three_employers):
    s, a, b, c = three_employers
    s.add_all(
        [
            SosEntity(
                employer_id=a.id,
                state="FL",
                registered_agent="John Doe",
                officers=[{"name": "Jane Smith", "title": "CEO"}],
            ),
            SosEntity(
                employer_id=b.id,
                state="FL",
                registered_agent="John Doe",
                officers=[{"name": "Jane Smith", "title": "Director"}],
            ),
            SosEntity(
                employer_id=c.id,
                state="FL",
                registered_agent="Other Agent",
                officers=[{"name": "Other Person", "title": "Owner"}],
            ),
        ]
    )
    s.commit()

    assert build_agent_links() >= 1
    assert build_officer_links() >= 1

    rels = s.execute(
        select(EntityRelationship).where(
            EntityRelationship.relationship_type.in_(["SHARED_AGENT", "SHARED_OFFICER"])
        )
    ).scalars().all()
    assert len(rels) >= 2
