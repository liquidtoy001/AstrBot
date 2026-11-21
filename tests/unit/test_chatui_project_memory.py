from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text

from astrbot.core.astr_agent_runtime.main_agent import workspace as workspace_build
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.provider.entities import ProviderRequest
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService


@pytest_asyncio.fixture
async def projects(tmp_path, monkeypatch):
    """Yield a project service, its database and the workspaces root.

    Args:
        tmp_path: Temporary directory holding the database and workspaces.
        monkeypatch: Redirects the AstrBot workspaces root to ``tmp_path``.
    """
    workspaces = tmp_path / "workspaces"
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path", lambda: str(workspaces)
    )
    monkeypatch.setattr(
        workspace_build, "get_astrbot_workspaces_path", lambda: str(workspaces)
    )
    db = SQLiteDatabase(str(tmp_path / "projects.db"))
    await db.initialize()
    for session_id in ("s1", "s2", "outside"):
        await db.create_platform_session(creator="alice", session_id=session_id)
    try:
        yield ChatUIProjectService(db), db, workspaces
    finally:
        await db.engine.dispose()


async def system_prompt(db, session_id: str) -> str:
    """Build the workspace part of the system prompt of one conversation.

    Args:
        db: Database holding the conversation and its project.
        session_id: ChatUI session ID of user ``alice``.

    Returns:
        The system prompt after the workspace instructions were applied.
    """
    req = ProviderRequest(prompt="hi", system_prompt="Base")
    await workspace_build.apply_workspace_instructions(
        SimpleNamespace(
            unified_msg_origin=f"webchat:FriendMessage:webchat!alice!{session_id}"
        ),
        req,
        SimpleNamespace(_db=db),
    )
    return req.system_prompt


@pytest.mark.asyncio
async def test_conversations_of_a_project_share_its_memory_file(projects):
    service, db, workspaces = projects
    # Each conversation keeps its own workspace, yet they share one file.
    project = await service.create_project(
        "alice", {"title": "P", "workspace_type": "session", "shared_memory": True}
    )
    memory_file = workspaces / f"project_{project['project_id']}" / "MEMORY.md"
    assert project["shared_memory"] is True
    assert project["memory_path"] == str(memory_file.resolve())
    await db.add_session_to_project("s1", project["project_id"])
    await db.add_session_to_project("s2", project["project_id"])

    # Before anything was remembered the Agent is still told where to write.
    prompt = await system_prompt(db, "s1")
    assert "[Project Shared Memory]" in prompt
    assert str(memory_file.resolve()) in prompt
    assert "(empty)" in prompt

    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("The user prefers metric units.", encoding="utf-8")
    for session_id in ("s1", "s2"):
        prompt = await system_prompt(db, session_id)
        assert prompt.startswith("Base")
        assert "The user prefers metric units." in prompt

    # A conversation outside the project does not see the memory.
    assert await system_prompt(db, "outside") == "Base"


@pytest.mark.asyncio
async def test_memory_is_added_only_while_the_project_shares_it(projects):
    service, db, workspaces = projects
    project = await service.create_project("alice", {"title": "P"})
    project_id = project["project_id"]
    assert project["shared_memory"] is False
    assert project["memory_path"] is None
    await db.add_session_to_project("s1", project_id)
    memory_file = workspaces / f"project_{project_id}" / "MEMORY.md"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("Remembered fact", encoding="utf-8")
    assert await system_prompt(db, "s1") == "Base"

    await service.update_project(
        "alice", {"project_id": project_id, "shared_memory": True}
    )
    assert "Remembered fact" in await system_prompt(db, "s1")

    # An update that does not mention the switch keeps it.
    await service.update_project("alice", {"project_id": project_id, "title": "Q"})
    assert (await service.get_project("alice", project_id))["shared_memory"] is True

    await service.update_project(
        "alice", {"project_id": project_id, "shared_memory": False}
    )
    assert await system_prompt(db, "s1") == "Base"


@pytest.mark.asyncio
async def test_memory_file_follows_a_custom_project_workspace(projects, tmp_path):
    service, db, _ = projects
    custom = tmp_path / "repo"
    custom.mkdir()
    (custom / "MEMORY.md").write_text("Deploys go out on Fridays.", encoding="utf-8")
    project = await service.create_project(
        "alice",
        {
            "title": "P",
            "workspace_type": "custom",
            "workspace_path": str(custom),
            "shared_memory": True,
        },
    )
    assert project["memory_path"] == str((custom / "MEMORY.md").resolve())
    await db.add_session_to_project("s1", project["project_id"])
    assert "Deploys go out on Fridays." in await system_prompt(db, "s1")


@pytest.mark.asyncio
async def test_long_memory_is_cut_and_the_agent_is_told(projects):
    service, db, workspaces = projects
    project = await service.create_project(
        "alice", {"title": "P", "shared_memory": True}
    )
    await db.add_session_to_project("s1", project["project_id"])
    memory_file = workspaces / f"project_{project['project_id']}" / "MEMORY.md"
    memory_file.parent.mkdir(parents=True)
    limit = workspace_build.PROJECT_MEMORY_MAX_CHARS
    memory_file.write_text("a" * limit + "TAIL", encoding="utf-8")

    prompt = await system_prompt(db, "s1")
    assert "a" * limit in prompt
    assert "TAIL" not in prompt
    assert "longer than what is shown" in prompt


@pytest.mark.asyncio
async def test_database_adds_shared_memory_column_to_old_schema(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "old.db"))
    await db.initialize()
    async with db.engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE chatui_projects DROP COLUMN shared_memory")
        )
        await conn.execute(
            text(
                "INSERT INTO chatui_projects "
                "(project_id, creator, title, workspace_type, created_at, updated_at) "
                "VALUES ('old', 'alice', 'Old', 'project', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    await db.initialize()
    assert (await db.get_chatui_project_by_id("old")).shared_memory is False
    await db.update_chatui_project("old", shared_memory=True)
    assert (await db.get_chatui_project_by_id("old")).shared_memory is True
    await db.engine.dispose()
