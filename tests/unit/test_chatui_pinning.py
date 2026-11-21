import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import text

from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.dashboard.services.chat_service import ChatService
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService


@pytest_asyncio.fixture
async def db(tmp_path):
    """Yield a database with three conversations of user ``alice``.

    Args:
        tmp_path: Temporary directory holding the database.
    """
    database = SQLiteDatabase(str(tmp_path / "pins.db"))
    await database.initialize()
    # Created oldest first, so "new" leads a list ordered by activity.
    for session_id in ("old", "mid", "new"):
        await database.create_platform_session(creator="alice", session_id=session_id)
        await asyncio.sleep(0.01)
    try:
        yield database
    finally:
        await database.engine.dispose()


async def listed(database, **kwargs) -> list[str]:
    """Return the session IDs of alice's first page of conversations.

    Args:
        database: Database to list from.
        **kwargs: Extra arguments of the paginated listing.

    Returns:
        Session IDs in listing order.
    """
    rows, _ = await database.get_platform_sessions_by_creator_paginated(
        creator="alice", **kwargs
    )
    return [row["session"].session_id for row in rows]


@pytest.mark.asyncio
async def test_pinned_conversation_is_listed_first_without_counting_as_activity(db):
    service = object.__new__(ChatService)
    service.db = db
    assert await listed(db) == ["new", "mid", "old"]
    before = (await db.get_platform_session_by_id("old")).updated_at

    await service.update_session("alice", "old", None, pinned=True)
    session = await db.get_platform_session_by_id("old")
    assert session.pinned is True
    # Pinning must not look like a new message.
    assert session.updated_at == before
    assert await listed(db) == ["old", "new", "mid"]
    # The pin survives paging: it leads the first page.
    assert await listed(db, page_size=1) == ["old"]

    # Renaming a pinned conversation keeps the pin and is activity as before.
    await service.update_session("alice", "old", "Renamed")
    session = await db.get_platform_session_by_id("old")
    assert session.pinned is True
    assert session.updated_at > before

    await service.update_session("alice", "old", None, pinned=False)
    await service.update_session("alice", "new", None)
    assert await listed(db) == ["new", "old", "mid"]


@pytest.mark.asyncio
async def test_pinned_conversation_leads_its_project(db):
    projects = ChatUIProjectService(db)
    project = await projects.create_project("alice", {"title": "P"})
    for session_id in ("old", "mid", "new"):
        await db.add_session_to_project(session_id, project["project_id"])
    await db.update_platform_session("mid", pinned=True)

    sessions = await projects.get_project_sessions("alice", project["project_id"])
    assert [session["session_id"] for session in sessions] == ["mid", "new", "old"]
    assert [session["pinned"] for session in sessions] == [True, False, False]


@pytest.mark.asyncio
async def test_pinned_project_conversation_is_also_listed_in_the_sidebar(db):
    projects = ChatUIProjectService(db)
    project = await projects.create_project("alice", {"title": "Docs"})
    await db.add_session_to_project("old", project["project_id"])
    await db.add_session_to_project("mid", project["project_id"])
    # Conversations inside a project stay out of the sidebar list.
    assert await listed(db, exclude_project_sessions=True) == ["new"]

    # Pinning one brings it back, first and with its project, so the sidebar
    # can show every pinned conversation in one group.
    await db.update_platform_session("old", pinned=True)
    assert await listed(db, exclude_project_sessions=True) == ["old", "new"]
    service = object.__new__(ChatService)
    service.db = db
    sessions = await service.get_sessions("alice", None)
    assert [
        (session["session_id"], session["project_id"], session["project_title"])
        for session in sessions
    ] == [("old", project["project_id"], "Docs"), ("new", None, None)]

    await db.update_platform_session("old", pinned=False)
    assert await listed(db, exclude_project_sessions=True) == ["new"]


@pytest.mark.asyncio
async def test_pinned_project_is_listed_first_without_counting_as_activity(db):
    projects = ChatUIProjectService(db)
    first = await projects.create_project("alice", {"title": "First"})
    await asyncio.sleep(0.01)
    second = await projects.create_project("alice", {"title": "Second"})
    assert first["pinned"] is False
    assert [p["title"] for p in await projects.list_projects("alice")] == [
        "Second",
        "First",
    ]

    await projects.update_project(
        "alice", {"project_id": first["project_id"], "pinned": True}
    )
    listed_projects = await projects.list_projects("alice")
    assert [p["title"] for p in listed_projects] == ["First", "Second"]
    assert listed_projects[0]["pinned"] is True
    assert listed_projects[0]["updated_at"] == first["updated_at"]

    # Editing something else keeps the pin.
    await projects.update_project(
        "alice", {"project_id": first["project_id"], "title": "Renamed"}
    )
    await projects.update_project(
        "alice", {"project_id": second["project_id"], "title": "Second again"}
    )
    assert [p["title"] for p in await projects.list_projects("alice")] == [
        "Renamed",
        "Second again",
    ]

    await projects.update_project(
        "alice", {"project_id": first["project_id"], "pinned": False}
    )
    assert [p["title"] for p in await projects.list_projects("alice")] == [
        "Second again",
        "Renamed",
    ]


@pytest.mark.asyncio
async def test_database_adds_pinned_columns_to_old_schema(tmp_path):
    database = SQLiteDatabase(str(tmp_path / "old.db"))
    await database.initialize()
    await database.create_platform_session(creator="alice", session_id="s1")
    project = await database.create_chatui_project(creator="alice", title="P")
    async with database.engine.begin() as conn:
        await conn.execute(text("ALTER TABLE platform_sessions DROP COLUMN pinned"))
        await conn.execute(text("ALTER TABLE chatui_projects DROP COLUMN pinned"))
    await database.initialize()
    assert (await database.get_platform_session_by_id("s1")).pinned is False
    assert (await database.get_chatui_project_by_id(project.project_id)).pinned is False
    await database.update_platform_session("s1", pinned=True)
    assert (await database.get_platform_session_by_id("s1")).pinned is True
    await database.engine.dispose()
