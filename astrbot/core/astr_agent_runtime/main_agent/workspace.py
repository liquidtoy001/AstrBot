"""Session workspace resolution and workspace-provided instructions."""

from __future__ import annotations

from pathlib import Path

from astrbot.core import logger
from astrbot.core.db import BaseDatabase
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path
from astrbot.core.workspace import (
    normalize_umo_for_workspace,
    parse_webchat_umo,
    project_memory_file,
    resolve_workspace_root_for_umo,
)

# Longest part of a project's MEMORY.md added to the system prompt.
PROJECT_MEMORY_MAX_CHARS = 8000


async def resolve_workspace_path(umo: str, plugin_context: Context) -> Path:
    """Resolve the workspace path for the current request.

    Args:
        umo: Unified message origin.
        plugin_context: Star context containing the database instance.

    Returns:
        Workspace path used as cwd.
    """
    fallback_root = (
        Path(get_astrbot_workspaces_path()) / normalize_umo_for_workspace(umo)
    ).resolve(strict=False)
    db = getattr(plugin_context, "_db", None)
    if not isinstance(db, BaseDatabase):
        return fallback_root
    try:
        return await resolve_workspace_root_for_umo(umo, db)
    except Exception:
        return fallback_root


async def apply_workspace_instructions(
    event: AstrMessageEvent,
    req: ProviderRequest,
    plugin_context: Context,
) -> None:
    """Append the workspace's EXTRA_PROMPT.md and the project's shared memory.

    The shared memory is the ``MEMORY.md`` of the conversation's ChatUI project
    and is added only when the project has shared memory turned on.

    Args:
        event: Event identifying the workspace's session.
        req: Request receiving the workspace instructions.
        plugin_context: Workspace resolution services.
    """
    workspace_root = await resolve_workspace_path(
        event.unified_msg_origin,
        plugin_context,
    )
    extra_prompts: list[str] = []
    extra_prompt_path = workspace_root / "EXTRA_PROMPT.md"
    if extra_prompt_path.is_file():
        try:
            extra_prompt = extra_prompt_path.read_text(encoding="utf-8").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to read workspace extra prompt for umo=%s from %s: %s",
                event.unified_msg_origin,
                extra_prompt_path,
                exc,
            )
        else:
            if extra_prompt:
                extra_prompts.append(f"From `{extra_prompt_path}`:\n{extra_prompt}")

    if extra_prompts:
        extra_prompt_text = "\n\n".join(extra_prompts)
        req.system_prompt = (
            f"{req.system_prompt or ''}\n"
            "[Workspace Extra Prompt]\n"
            "The following instructions are loaded from the current workspace "
            "`EXTRA_PROMPT.md` file.\n"
            f"{extra_prompt_text}\n"
        )

    parsed = parse_webchat_umo(event.unified_msg_origin)
    db = getattr(plugin_context, "_db", None)
    if not parsed or not isinstance(db, BaseDatabase):
        return
    creator, session_id = parsed
    try:
        project = await db.get_project_by_session(
            session_id=session_id, creator=creator
        )
        if not project or not project.shared_memory:
            return
        memory_path = project_memory_file(project)
        memory = (
            memory_path.read_text(encoding="utf-8").strip()
            if memory_path.is_file()
            else ""
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to read project memory for umo=%s: %s",
            event.unified_msg_origin,
            exc,
        )
        return
    if len(memory) > PROJECT_MEMORY_MAX_CHARS:
        memory = (
            f"{memory[:PROJECT_MEMORY_MAX_CHARS]}\n"
            "[The file is longer than what is shown here. Shorten it.]"
        )
    req.system_prompt = (
        f"{req.system_prompt or ''}\n"
        "[Project Shared Memory]\n"
        "All conversations in this project share the memory file "
        f"`{memory_path}`. Its current content:\n"
        f"{memory or '(empty)'}\n"
        "When you learn something worth keeping for later conversations in "
        "this project, such as a decision, a user preference or a lasting "
        "fact, and you have file tools that can write to that file, add it "
        "there. Keep the file short and remove entries that are no longer "
        "true.\n"
    )
