"""ChatUI file change preview and single-file undo."""

import os
import pathlib

import pytest

from astrbot.core.astr_agent_runtime.tools.computer_tools import file_undo

USER = "alice"
OWNER = (USER, "webchat!alice!conv-1")


@pytest.fixture(autouse=True)
def journal_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(file_undo, "_journal_dir", lambda: tmp_path / "journal")


def test_edit_preview_is_bounded_region_and_undo_restores(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text("one\nTWO\nthree\nfour\n", encoding="utf-8")

    meta = file_undo.record_change(str(target), before, *OWNER)

    assert meta["undoable"] is True
    assert meta["start_line"] == 2
    assert meta["removed"] == ["two"]
    assert meta["added"] == ["TWO"]
    ok, _ = file_undo.undo_change(meta["change_id"], USER)
    assert ok
    assert target.read_text(encoding="utf-8") == "one\ntwo\nthree\nfour\n"
    # The journal entry is consumed: a second undo fails closed.
    ok, _ = file_undo.undo_change(meta["change_id"], USER)
    assert not ok


def test_undo_refused_when_file_changed_since(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text("new", encoding="utf-8")
    meta = file_undo.record_change(str(target), before, *OWNER)
    target.write_text("edited by user", encoding="utf-8")

    ok, message = file_undo.undo_change(meta["change_id"], USER)

    assert not ok
    assert "changed" in message
    assert target.read_text(encoding="utf-8") == "edited by user"


def test_undo_of_created_file_deletes_it(tmp_path):
    target = tmp_path / "new.txt"
    before = file_undo.snapshot_before(str(target))
    target.write_text("hello\n", encoding="utf-8")

    meta = file_undo.record_change(str(target), before, *OWNER)

    assert meta["created"] is True
    assert meta["added"] == ["hello"]
    ok, _ = file_undo.undo_change(meta["change_id"], USER)
    assert ok
    assert not target.exists()


def test_large_and_binary_files_get_no_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(file_undo, "MAX_SNAPSHOT_BYTES", 8)
    big = tmp_path / "big.txt"
    big.write_text("0123456789", encoding="utf-8")
    meta = file_undo.record_change(
        str(big), file_undo.snapshot_before(str(big)), *OWNER
    )
    assert meta == {
        "path": str(big),
        "created": False,
        "undoable": False,
        "reason": "too_large",
    }

    binary = tmp_path / "b.bin"
    binary.write_bytes(b"\xff\xfe")
    before = file_undo.snapshot_before(str(binary))
    binary.write_bytes(b"\xff\x00")
    meta = file_undo.record_change(str(binary), before, *OWNER)
    assert meta["undoable"] is False
    assert meta["reason"] == "binary"


def test_preview_is_truncated(tmp_path):
    target = tmp_path / "a.txt"
    before = file_undo.snapshot_before(str(target))
    target.write_text("\n".join(str(i) for i in range(100)), encoding="utf-8")

    meta = file_undo.record_change(str(target), before, *OWNER)

    assert meta["truncated"] is True
    assert len(meta["added"]) == file_undo.MAX_PREVIEW_LINES
    assert meta["added_count"] == 100


@pytest.mark.parametrize("change_id", ["../../etc/passwd", "", "ABC", "0" * 31])
def test_invalid_change_id_rejected(change_id):
    ok, _ = file_undo.undo_change(change_id, USER)
    assert not ok


@pytest.mark.asyncio
async def test_webchat_tool_result_carries_file_change_into_history():
    """The preview rides on the webchat tool result and is saved, not modelled."""
    import json
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from astrbot.core.agent.events import ToolFinished, ToolStarted, TurnStatus
    from astrbot.core.agent_output import present_turn
    from astrbot.dashboard.services.chat_service import BotMessageAccumulator

    preview = {"path": "a.txt", "undoable": True, "change_id": "0" * 32}
    sent = []

    async def send(chain):
        sent.append(chain)

    event = SimpleNamespace(
        get_platform_name=lambda: "webchat",
        send=send,
        trace=SimpleNamespace(record=lambda *a, **k: None),
    )
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def events():
        yield SimpleNamespace(
            payload=ToolStarted(
                execution_id="e1", call_id="call_1", name="write", arguments={}
            ),
            created_at=at,
        )
        yield SimpleNamespace(
            payload=ToolFinished(
                execution_id="e1",
                call_id="call_1",
                status=TurnStatus.COMPLETED,
                structured_result={"file_change": preview},
            ),
            created_at=at,
        )

    turn = SimpleNamespace(input=SimpleNamespace(event=event), events=events)
    [chain async for chain in present_turn(turn, streaming=False)]

    result = next(c for c in sent if c.type == "tool_call_result").chain[0].data
    assert result["file_change"] == preview

    accumulator = BotMessageAccumulator()
    accumulator.add_plain(
        json.dumps({"id": "call_1", "name": "write", "ts": 1}),
        chain_type="tool_call",
        streaming=False,
    )
    accumulator.add_plain(
        json.dumps(result), chain_type="tool_call_result", streaming=False
    )
    saved = accumulator.build_message_parts()[0]["tool_calls"][0]
    assert saved["file_change"] == preview


def test_only_the_owner_of_the_conversation_can_undo(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text("new", encoding="utf-8")
    meta = file_undo.record_change(str(target), before, *OWNER)

    ok, message = file_undo.undo_change(meta["change_id"], "mallory")
    assert not ok and "another user" in message
    # An entry whose conversation is not the owner's own is refused too.
    forged = file_undo.record_change(str(target), b"x", USER, "webchat!bob!conv")
    assert not file_undo.undo_change(forged["change_id"], USER)[0]
    assert target.read_text(encoding="utf-8") == "new"

    assert file_undo.undo_change(meta["change_id"], USER)[0]
    assert target.read_text(encoding="utf-8") == "old"


def test_undo_refused_when_file_was_replaced_by_a_symlink(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text("new", encoding="utf-8")
    meta = file_undo.record_change(str(target), before, *OWNER)

    outside = tmp_path / "outside.txt"
    outside.write_text("new", encoding="utf-8")  # same bytes as the after-state
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available")

    ok, message = file_undo.undo_change(meta["change_id"], USER)

    assert not ok and "replaced" in message
    assert outside.read_text(encoding="utf-8") == "new"


def test_symlinks_get_no_undo(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("old", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks are not available")

    assert file_undo.snapshot_before(str(link)) == "unreadable"


def test_undo_replaces_the_file_atomically(tmp_path, monkeypatch):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text("new", encoding="utf-8")
    meta = file_undo.record_change(str(target), before, *OWNER)
    replaced = []
    real_replace = file_undo.os.replace

    def spy(src, dst):
        replaced.append((pathlib.Path(src).parent, pathlib.Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(file_undo.os, "replace", spy)

    assert file_undo.undo_change(meta["change_id"], USER)[0]
    assert replaced == [(tmp_path, target)]
    assert target.read_text(encoding="utf-8") == "old"
    assert sorted(x.name for x in tmp_path.iterdir()) == ["a.txt", "journal"]


def test_undo_refuses_deleted_target(tmp_path):
    target = tmp_path / "gone.txt"
    target.write_text("before", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text("after", encoding="utf-8")
    change = file_undo.record_change(str(target), before, *OWNER)
    target.unlink()
    assert not file_undo.undo_change(change["change_id"], USER)[0]
    assert not target.exists()


def test_journal_prunes_the_oldest_entries_beyond_the_cap(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr(file_undo, "MAX_JOURNAL_ENTRIES", 3)
    target = tmp_path / "many.txt"
    ids = []
    for index in range(4):
        before = file_undo.snapshot_before(str(target))
        target.write_text(str(index), encoding="utf-8")
        change = file_undo.record_change(str(target), before, *OWNER)
        ids.append(change["change_id"])
        os.utime(
            file_undo._journal_dir() / (ids[-1] + ".json"), (1000 + index, 1000 + index)
        )
    entries = list(file_undo._journal_dir().glob("*.json"))
    assert len(entries) == 3
    assert not (file_undo._journal_dir() / (ids[0] + ".json")).exists()
    assert file_undo.undo_change(ids[-1], USER)[0]
    assert target.read_text(encoding="utf-8") == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("thread", [False, True])
async def test_deleting_a_conversation_removes_its_undo_snapshots(tmp_path, thread):
    import json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from astrbot.dashboard.services.chat_service import ChatService

    journal = tmp_path / "journal"
    journal.mkdir()
    for name, conversation in [("owned", "gone"), ("other", "keep")]:
        (journal / f"{name}.json").write_text(
            json.dumps(
                {"owner": USER, "conversation": f"webchat!{USER}!{conversation}"}
            ),
            encoding="utf-8",
        )
    service = object.__new__(ChatService)
    service.chat_runs_by_session = {}
    service.running_convs = {}
    service.conv_mgr = SimpleNamespace(delete_conversations_by_user_id=AsyncMock())
    service.platform_history_mgr = SimpleNamespace(
        get=AsyncMock(return_value=[]), delete=AsyncMock()
    )
    service.umop_config_router = SimpleNamespace(delete_route=AsyncMock())
    service.db = SimpleNamespace(
        delete_webchat_threads_by_parent_session=AsyncMock(return_value=[]),
        delete_platform_session=AsyncMock(),
    )
    if thread:
        await service.delete_threads_by_ids(["gone"], USER)
    else:
        await service.delete_session_internal(
            SimpleNamespace(session_id="gone", platform_id="webchat", is_group=False),
            USER,
        )
    assert not (journal / "owned.json").exists()
    assert (journal / "other.json").exists()


def test_preview_path_never_shows_the_home_directory(tmp_path, monkeypatch):
    """The card gets a display path; only the journal keeps the real one."""
    home = tmp_path / "home"
    workspace = home / "data" / "workspaces" / "conv"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(file_undo.Path, "home", classmethod(lambda cls: home))
    inside = workspace / "notes" / "a.txt"
    inside.parent.mkdir()
    in_home = home / "b.txt"
    elsewhere = tmp_path / "c.txt"
    for target in (inside, in_home, elsewhere):
        before = file_undo.snapshot_before(str(target))
        target.write_text("x\n", encoding="utf-8")
        meta = file_undo.record_change(str(target), before, *OWNER, workspace=workspace)
        expected = {
            inside: "notes/a.txt",
            in_home: "~/b.txt",
            elsewhere: str(elsewhere),
        }[target]
        assert meta["path"] == expected
        # Undo still works from the journal's real path.
        ok, _ = file_undo.undo_change(meta["change_id"], USER)
        assert ok
        assert not target.exists()


# Each undo safety check, caught on its own.


def _link_dir(link, target):
    """Make ``link`` point at directory ``target`` (a junction on Windows)."""
    try:
        if os.name == "nt":
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("directory links are not available")


def _record(target, old="old", new="new"):
    target.write_text(old, encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text(new, encoding="utf-8")
    return file_undo.record_change(str(target), before, *OWNER)


def test_owner_must_match_even_inside_the_users_own_session_prefix(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    target.write_text("new", encoding="utf-8")
    # Recorded for bob, although the session ID names alice.
    change = file_undo.record_change(str(target), before, "bob", OWNER[1])

    ok, message = file_undo.undo_change(change["change_id"], USER)

    assert not ok and "another user" in message
    assert target.read_text(encoding="utf-8") == "new"


def test_undo_refused_when_a_parent_directory_was_replaced(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    change = _record(folder / "a.txt")
    # Same name and same bytes, but the folder now leads somewhere else; the
    # path itself is not a symlink, so only the real-path check sees it.
    other = tmp_path / "other"
    other.mkdir()
    (other / "a.txt").write_text("new", encoding="utf-8")
    folder.rename(tmp_path / "moved")
    _link_dir(folder, other)

    ok, message = file_undo.undo_change(change["change_id"], USER)

    assert not ok and "replaced" in message
    assert (other / "a.txt").read_text(encoding="utf-8") == "new"


def test_undo_refused_when_the_path_became_a_link_to_the_same_file(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    via = tmp_path / "via"
    _link_dir(via, real)
    # Recorded through a linked folder: the real path is real/a.txt.
    change = _record(via / "a.txt")
    if os.name == "nt":
        os.rmdir(via)  # removes the junction, not its target
    else:
        via.unlink()
    via.mkdir()
    try:
        (via / "a.txt").symlink_to(real / "a.txt")
    except OSError:
        pytest.skip("symlinks are not available")
    # Same real path and bytes: only the symlink check refuses it.

    ok, message = file_undo.undo_change(change["change_id"], USER)

    assert not ok and "replaced" in message
    assert (real / "a.txt").read_text(encoding="utf-8") == "new"


def test_path_that_became_a_symlink_after_the_snapshot_gets_no_undo(tmp_path):
    target = tmp_path / "a.txt"
    target.write_text("old", encoding="utf-8")
    before = file_undo.snapshot_before(str(target))
    outside = tmp_path / "outside.txt"
    outside.write_text("new", encoding="utf-8")
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available")

    change = file_undo.record_change(str(target), before, *OWNER)

    assert change["undoable"] is False
    assert change["reason"] == "unreadable"
    assert not list(file_undo._journal_dir().glob("*.json"))
