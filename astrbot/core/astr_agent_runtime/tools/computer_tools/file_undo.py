"""Change preview and single-file undo for ChatUI file write/edit tools.

Only used for the local computer runtime on the webchat platform. Before a
write or edit the file tool captures the current bytes; after it succeeds the
change is recorded in a journal under the AstrBot data directory (outside any
workspace) and a bounded preview is returned as the tool's structured content,
which reaches the ChatUI tool call card but not the model context.
Undo is allowed only for the dashboard user who made the change (from any of
their own ChatUI conversations), and restores the captured bytes only if the
file is still the same regular file (no symlink, same real path) with the
recorded after-state; it writes through a temporary file and an atomic
replace, and fails closed otherwise.

The journal keeps the full previous content (base64), so it holds at most
MAX_JOURNAL_ENTRIES x MAX_SNAPSHOT_BYTES of snapshots: about 200 MB on disk
in the worst case (300 entries of 512 KB), usually far less.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

import mcp

from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

MAX_SNAPSHOT_BYTES = 512 * 1024
"""Files larger than this (before or after) get no preview and no undo."""
MAX_PREVIEW_LINES = 40
"""Maximum lines shown per side of the changed region."""
MAX_JOURNAL_ENTRIES = 300
"""Oldest journal entries beyond this count are pruned."""

_CHANGE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
# Snapshot markers: the file did not exist yet, or no snapshot could be taken
# (the value doubles as the preview's ``reason``).
_MISSING = "missing"
_TOO_LARGE = "too_large"
_UNREADABLE = "unreadable"


def _journal_dir() -> Path:
    return Path(get_astrbot_data_path()) / "chatui_file_undo"


def snapshot_before(path: str) -> bytes | str:
    """Capture a file's bytes before the tool changes it.

    Args:
        path: Absolute local path the tool is about to write.

    Returns:
        The file bytes, ``"missing"`` if the file does not exist yet, or
        ``"too_large"`` / ``"unreadable"`` (a link, not a regular file, or a
        read error) when no snapshot can be taken, which disables preview and
        undo for this call.
    """
    target = Path(path)
    try:
        if target.is_symlink():
            # Undo would have to write through the link; leave it alone.
            return _UNREADABLE
        if not target.exists():
            return _MISSING
        if not target.is_file():
            return _UNREADABLE
        if target.stat().st_size > MAX_SNAPSHOT_BYTES:
            return _TOO_LARGE
        return target.read_bytes()
    except OSError:
        return _UNREADABLE


def record_change(
    path: str,
    before: bytes | str,
    owner: str,
    conversation: str,
    workspace: str | Path | None = None,
) -> dict:
    """Journal a completed write/edit and build its ChatUI preview.

    Args:
        path: Absolute local path that was written.
        before: Value returned by :func:`snapshot_before` for this path.
        owner: Sender ID (the dashboard username) that made the change.
        conversation: WebChat session ID (``webchat!<user>!<conversation>``).
        workspace: The conversation's workspace root, if known.

    Returns:
        Preview dict for the tool call card. Its ``path`` is for display only:
        relative to ``workspace`` when the file is inside it, ``~/...`` under
        the home directory, otherwise absolute. Undo uses the journal.
        ``undoable`` is False with a ``reason`` (``too_large``,
        ``unreadable`` or ``binary``) when no undo was recorded.
    """
    # Show as little of the machine's layout as the card needs: never the
    # account's home directory.
    display_path = path
    for base, prefix in ((workspace, ""), (Path.home(), "~/")):
        if not base:
            continue
        try:
            relative = Path(path).resolve().relative_to(Path(base).resolve())
        except (OSError, ValueError):
            continue
        display_path = prefix + relative.as_posix()
        break
    meta: dict = {
        "path": display_path,
        "created": before == _MISSING,
        "undoable": False,
    }
    try:
        if Path(path).is_symlink():
            raise OSError("symlink")
        after = Path(path).read_bytes()
        real_path = str(Path(path).resolve(strict=True))
    except OSError:
        meta["reason"] = "unreadable"
        return meta
    if before in (_TOO_LARGE, _UNREADABLE):
        meta["reason"] = before
        return meta
    if len(after) > MAX_SNAPSHOT_BYTES:
        meta["reason"] = _TOO_LARGE
        return meta
    before_bytes = b"" if before == _MISSING else before
    try:
        before_lines = before_bytes.decode("utf-8").splitlines()
        after_lines = after.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        meta["reason"] = "binary"
        return meta

    # One bounded changed region: strip the common prefix and suffix lines.
    start = 0
    limit = min(len(before_lines), len(after_lines))
    while start < limit and before_lines[start] == after_lines[start]:
        start += 1
    end = 0
    while (
        end < limit - start
        and before_lines[len(before_lines) - 1 - end]
        == after_lines[len(after_lines) - 1 - end]
    ):
        end += 1
    removed = before_lines[start : len(before_lines) - end]
    added = after_lines[start : len(after_lines) - end]
    meta.update(
        start_line=start + 1,
        removed=removed[:MAX_PREVIEW_LINES],
        added=added[:MAX_PREVIEW_LINES],
        removed_count=len(removed),
        added_count=len(added),
        truncated=len(removed) > MAX_PREVIEW_LINES or len(added) > MAX_PREVIEW_LINES,
    )

    change_id = uuid.uuid4().hex
    journal = _journal_dir()
    journal.mkdir(parents=True, exist_ok=True)
    (journal / f"{change_id}.json").write_text(
        json.dumps(
            {
                "path": path,
                "real_path": real_path,
                "owner": owner,
                "conversation": conversation,
                "before": None
                if before == _MISSING
                else base64.b64encode(before_bytes).decode("ascii"),
                "after_sha256": hashlib.sha256(after).hexdigest(),
                "created_at": time.time(),
            }
        ),
        encoding="utf-8",
    )
    entries = sorted(journal.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for old in entries[:-MAX_JOURNAL_ENTRIES]:
        old.unlink(missing_ok=True)
    meta.update(change_id=change_id, undoable=True)
    return meta


def track_chatui_change(event, local_env: bool, path: str) -> tuple[bool, object]:
    """Decide whether a file write/edit gets a ChatUI preview, and snapshot it.

    Args:
        event: The event the tool call runs with.
        local_env: Whether the tool runs in the local computer runtime.
        path: Absolute local path the tool is about to write.

    Returns:
        ``(track, before)``: whether to record the change, and the value of
        :func:`snapshot_before` to pass to :func:`chatui_tool_result`.
    """
    if not local_env or event.get_platform_name() != "webchat":
        return False, None
    return True, snapshot_before(path)


def chatui_tool_result(message: str, event, path: str, before, workspace=None):
    """Record a completed write/edit and attach its preview for ChatUI.

    The preview is structured content, which reaches the ChatUI tool call card
    but not the model; the model only sees ``message``.

    Args:
        message: The tool's text result.
        event: The event the tool call runs with.
        path: Absolute local path that was written.
        before: Value returned by :func:`track_chatui_change`.
        workspace: The conversation's workspace root, for the display path.

    Returns:
        A tool result with the preview, or ``message`` if recording failed.
    """
    try:
        return mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text=message)],
            structuredContent={
                "file_change": record_change(
                    path,
                    before,
                    owner=event.get_sender_id(),
                    conversation=event.session_id,
                    workspace=workspace,
                )
            },
        )
    except Exception as exc:
        logger.warning(f"Failed to record file change for undo: {exc}")
        return message


def clear_conversation_changes(username: str, conversation: str) -> None:
    """Remove undo snapshots belonging to a deleted conversation.

    Args:
        username: Authenticated owner of the conversation.
        conversation: Exact WebChat session identity to remove.
    """
    for entry_path in _journal_dir().glob("*.json"):
        if entry_path.is_symlink():
            continue
        try:
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            if (
                isinstance(entry, dict)
                and entry.get("owner") == username
                and entry.get("conversation") == conversation
            ):
                entry_path.unlink(missing_ok=True)
        except (OSError, ValueError):
            continue


def undo_change(change_id: str, username: str) -> tuple[bool, str]:
    """Restore a file to its state before a recorded change.

    Args:
        change_id: Journal id from the preview.
        username: Authenticated dashboard user asking for the undo.

    Returns:
        ``(ok, message)``. Undo is refused when the entry is unknown, was
        already used or belongs to another user or conversation, or when the
        file is no longer the same regular file with the after-state.
    """
    if not _CHANGE_ID_RE.match(change_id or ""):
        return False, "Invalid change id."
    entry_path = _journal_dir() / f"{change_id}.json"
    try:
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "This change cannot be undone (no record, or already undone)."
    # Entries from before ownership was recorded have no owner and fail here.
    if (
        not username
        or entry.get("owner") != username
        or not str(entry.get("conversation") or "").startswith(f"webchat!{username}!")
    ):
        return False, "This change was made in another user's conversation."
    target = Path(entry["path"])
    try:
        # A symlink or a different real path means the file was replaced.
        if target.is_symlink() or str(target.resolve(strict=True)) != entry.get(
            "real_path"
        ):
            return False, "The file has been moved or replaced; undo refused."
        current = target.read_bytes() if target.is_file() else None
    except OSError:
        current = None
    if current is None or hashlib.sha256(current).hexdigest() != entry["after_sha256"]:
        return False, "The file has changed since this edit; undo refused."
    try:
        if entry["before"] is None:
            target.unlink()
        else:
            # Write a sibling temp file, then replace atomically: os.replace
            # swaps the directory entry and never writes through a link.
            fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".undo-")
            try:
                with os.fdopen(fd, "wb") as tmp:
                    tmp.write(base64.b64decode(entry["before"]))
                os.chmod(tmp_name, target.stat().st_mode & 0o7777)
                os.replace(tmp_name, target)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise
    except OSError as exc:
        return False, f"Undo failed: {exc}"
    entry_path.unlink(missing_ok=True)
    return True, (
        f"Deleted {target} (it was created by this edit)."
        if entry["before"] is None
        else f"Restored {target}."
    )
