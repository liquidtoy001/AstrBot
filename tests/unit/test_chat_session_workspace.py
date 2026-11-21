import pytest
import pytest_asyncio
from sqlalchemy import text

from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.workspace import (
    default_workspace_root,
    project_workspace_root,
    resolve_workspace_root_for_umo,
)
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError
from astrbot.dashboard.services.chatui_project_service import ChatUIProjectService

UMO = "webchat:FriendMessage:webchat!alice!s1"


@pytest_asyncio.fixture
async def chat(tmp_path, monkeypatch):
    """Yield a chat service, its database and an existing directory.

    Args:
        tmp_path: Temporary directory holding the database and workspaces.
        monkeypatch: Redirects the AstrBot workspaces root to ``tmp_path``.
    """
    monkeypatch.setattr(
        "astrbot.core.workspace.get_astrbot_workspaces_path",
        lambda: str(tmp_path / "workspaces"),
    )
    (tmp_path / "workspaces" / "shared").mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    db = SQLiteDatabase(str(tmp_path / "sessions.db"))
    await db.initialize()
    service = object.__new__(ChatService)
    service.db = db
    await db.create_platform_session(creator="alice", session_id="s1")
    try:
        yield service, db, external
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_session_workspace_path_overrides_default_and_project(chat):
    service, db, external = chat
    assert await resolve_workspace_root_for_umo(UMO, db) == default_workspace_root(UMO)

    await service.update_session("alice", "s1", None, str(external))
    assert await resolve_workspace_root_for_umo(UMO, db) == external.resolve()
    session = await db.get_platform_session_by_id("s1")
    assert session.workspace_path == str(external)

    # The conversation's own path wins over its project's shared workspace.
    project = await db.create_chatui_project(
        creator="alice", title="P", workspace_type="project"
    )
    await db.add_session_to_project("s1", project.project_id)
    assert await resolve_workspace_root_for_umo(UMO, db) == external.resolve()

    # An empty string restores the project workspace.
    await service.update_session("alice", "s1", None, "")
    assert (await db.get_platform_session_by_id("s1")).workspace_path is None
    assert await resolve_workspace_root_for_umo(UMO, db) == project_workspace_root(
        project.project_id
    )


@pytest.mark.asyncio
async def test_session_workspace_relative_path_points_into_workspaces(chat, tmp_path):
    service, db, _ = chat
    await service.update_session("alice", "s1", None, " shared ")
    assert (
        await resolve_workspace_root_for_umo(UMO, db)
        == (tmp_path / "workspaces" / "shared").resolve()
    )


@pytest.mark.asyncio
async def test_rename_keeps_workspace_path(chat):
    service, db, external = chat
    await service.update_session("alice", "s1", None, str(external))
    await service.update_session("alice", "s1", "Renamed")
    session = await db.get_platform_session_by_id("s1")
    assert session.display_name == "Renamed"
    assert session.workspace_path == str(external)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "message"),
    [("missing", "does not exist"), ("../outside", "must stay within")],
)
async def test_session_workspace_rejects_unusable_path(chat, path, message):
    service, db, _ = chat
    with pytest.raises(ChatServiceError, match=message):
        await service.update_session("alice", "s1", None, path)
    assert (await db.get_platform_session_by_id("s1")).workspace_path is None


@pytest.mark.asyncio
async def test_session_workspace_requires_owner(chat):
    service, db, external = chat
    with pytest.raises(ChatServiceError, match="Permission denied"):
        await service.update_session("bob", "s1", None, str(external))


@pytest.mark.asyncio
async def test_api_key_session_cannot_use_workspace_path(chat):
    service, db, external = chat
    await db.create_platform_session(creator="api_key:k1", session_id="k1-session")
    with pytest.raises(ChatServiceError, match="API key sessions"):
        await service.update_session("api_key:k1", "k1-session", None, str(external))

    # A path written by other means is ignored for API key conversations.
    await db.update_platform_session("k1-session", workspace_path=str(external))
    umo = "webchat:FriendMessage:webchat!api_key:k1!k1-session"
    assert await resolve_workspace_root_for_umo(umo, db) == default_workspace_root(umo)


@pytest.mark.asyncio
async def test_project_files_panel_follows_session_workspace_path(chat):
    service, db, external = chat
    (external / "note.txt").write_text("from conversation", encoding="utf-8")
    project = await db.create_chatui_project(
        creator="alice", title="P", workspace_type="project"
    )
    await db.add_session_to_project("s1", project.project_id)
    await service.update_session("alice", "s1", None, str(external))
    projects = ChatUIProjectService(db)

    listing = await projects.list_workspace_files(
        "alice", project.project_id, session_id="s1"
    )
    assert [entry["name"] for entry in listing["entries"]] == ["note.txt"]
    preview = await projects.get_workspace_file(
        "alice", project.project_id, "note.txt", "s1"
    )
    assert preview["content"] == "from conversation"
    # Without the conversation, the panel still shows the project workspace.
    assert (await projects.list_workspace_files("alice", project.project_id))[
        "entries"
    ] == []
    sessions = await projects.get_project_sessions("alice", project.project_id)
    assert sessions[0]["workspace_path"] == str(external)


@pytest.mark.asyncio
async def test_database_adds_session_workspace_column_to_old_schema(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "old.db"))
    await db.initialize()
    async with db.engine.begin() as conn:
        await conn.execute(
            text("ALTER TABLE platform_sessions DROP COLUMN workspace_path")
        )
    await db.initialize()
    await db.create_platform_session(creator="alice", session_id="s1")
    await db.update_platform_session("s1", workspace_path="shared")
    assert (await db.get_platform_session_by_id("s1")).workspace_path == "shared"
    await db.engine.dispose()
