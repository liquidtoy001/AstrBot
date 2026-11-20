"""Agent configuration persistence, profile authorization and migration."""

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.agent.config_store import AgentConfigStore
from astrbot.core.astr_agent_runtime.main_agent.subagent import apply_subagents
from astrbot.core.config.agent import normalize_agent
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.db.migration.migra_agent_configs import migrate_agent_configs
from astrbot.core.provider.entities import ProviderRequest
from astrbot.dashboard.responses import ApiError
from astrbot.dashboard.services.agent_config_service import AgentConfigService


@pytest.mark.asyncio
async def test_config_crud_uses_stable_ids_and_blocks_persisted_references(environment):
    env = environment
    profile = env.context.get_config()
    core = SimpleNamespace(
        star_context=env.context,
        agent_configs=env.agent_configs,
        agent_runtimes=env.runtimes,
        astrbot_config_mgr=SimpleNamespace(confs={"default": profile}),
    )
    service = AgentConfigService(
        env.agent_configs, env.runtimes, core.astrbot_config_mgr
    )
    created = await service.save(
        {"name": "Researcher", "runtime": "memory", "config": {"model": "external"}}
    )
    config_id = created["config_id"]
    profile["agent"]["config"]["subagents"]["config_ids"] = [config_id]
    renamed = await service.save(
        {
            **{key: value for key, value in created.items() if key != "config_id"},
            "name": "Renamed",
        },
        config_id,
    )
    assert renamed["config_id"] == config_id
    with pytest.raises(ApiError) as rejected:
        await service.delete(config_id)
    assert rejected.value.data["references"] == [{"type": "profile", "id": "default"}]
    profile["agent"]["config"]["subagents"]["config_ids"] = []
    env.memory.referenced_config_ids = lambda config: config.get("targets", [])
    parent = await service.save(
        {
            "name": "Parent",
            "runtime": "memory",
            "config": {"targets": [config_id]},
        }
    )
    with pytest.raises(ApiError) as rejected:
        await service.delete(config_id)
    assert rejected.value.data["references"][0]["id"] == parent["config_id"]
    await service.delete(parent["config_id"])
    await service.delete(config_id)
    assert await service.list() == []
    with pytest.raises(ValueError, match="unavailable"):
        await service.save({"name": "Unknown", "runtime": "missing"})


@pytest.mark.asyncio
async def test_profile_selection_is_enforced_in_prompt_and_spawn(environment):
    env = environment
    chosen = await env.save_agent("Selected", runtime="memory")
    other = await env.save_agent("Unselected", runtime="memory")
    env.config["config_ids"] = [chosen.config_id]
    request = ProviderRequest(conversation=env.conversation)
    await apply_subagents(request, env.context, env.event, runtime=env.native)
    tool_schema = request.func_tool.openai_schema()
    assert chosen.config_id in request.system_prompt
    assert other.config_id not in request.system_prompt
    registered = env.runtimes.pop("memory")
    unavailable = ProviderRequest(conversation=env.conversation)
    assert await apply_subagents(
        unavailable, env.context, env.event, runtime=env.native
    )
    assert chosen.config_id not in unavailable.system_prompt
    env.runtimes["memory"] = registered
    with pytest.raises(ValueError, match="not selected"):
        await env.native.spawn_agent(
            env.root, [{"type": "plain", "text": "Task"}], config_id=other.config_id
        )
    chosen.enabled = False
    await env.agent_configs.save(chosen)
    updated = ProviderRequest(conversation=env.conversation)
    await apply_subagents(updated, env.context, env.event, runtime=env.native)
    assert chosen.config_id not in updated.system_prompt
    assert updated.func_tool.openai_schema() == tool_schema
    with pytest.raises(ValueError, match="disabled"):
        await env.native.spawn_agent(
            env.root, [{"type": "plain", "text": "Task"}], config_id=chosen.config_id
        )
    env.config["config_ids"] = []
    generic = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Task"}]
    )
    await env.service.wait(env.root, [generic["agent_id"]], 2000, "all")
    assert env.store.agents[generic["agent_id"]].runtime == "astrbot"


@pytest.mark.asyncio
async def test_different_profiles_resolve_their_own_selection(environment):
    env = environment
    chosen = await env.save_agent("Only A", runtime="memory")
    profile_a = env.context.get_config()
    profile_b = copy.deepcopy(profile_a)
    profile_b["agent"]["config"]["subagents"]["config_ids"] = []
    requested_umos = []

    def get_config(**kwargs):
        requested_umos.append(kwargs.get("umo"))
        return profile_b

    env.context.get_config = get_config
    with pytest.raises(ValueError, match="not selected"):
        await env.native.spawn_agent(
            env.root, [{"type": "plain", "text": "Task"}], config_id=chosen.config_id
        )
    assert requested_umos == [env.scope.umo]


@pytest.mark.asyncio
async def test_config_migration_keeps_source_on_failure_and_is_idempotent(
    environment, monkeypatch, tmp_path
):
    env = environment
    data_path = tmp_path / "data"
    profile_path = data_path / "config"
    profile_path.mkdir(parents=True)
    monkeypatch.setattr(
        "astrbot.core.utils.migra_helper.get_astrbot_data_path", lambda: str(data_path)
    )
    monkeypatch.setattr(
        "astrbot.core.utils.migra_helper.get_astrbot_config_path",
        lambda: str(profile_path),
    )
    legacy = {
        "main_enable": True,
        "max_concurrent_agents": 2,
        "task_timeout": 123,
        "agents": [{"name": "planner"}, {"name": "researcher"}],
    }
    paths = [data_path / "cmd_config.json", profile_path / "abconf_a.json"]
    for index, path in enumerate(paths):
        path.write_text(
            json.dumps(
                {
                    "config_version": 4,
                    "agent_runner": {
                        "runner_type": "local",
                        "config": {
                            "model": {"provider_id": f"model-{index}"},
                        },
                    },
                    "subagent_orchestrator": legacy,
                }
            ),
            encoding="utf-8",
        )
    profiles = [AstrBotConfig(str(path)) for path in paths]
    pending = paths[0].with_suffix(".subagents-migration.json")
    assert json.loads(pending.read_text(encoding="utf-8")) == legacy
    selection = profiles[0]["agent"]["config"]["subagents"]
    assert selection == {
        "enabled": True,
        "config_ids": selection["config_ids"],
        "max_concurrent_agents": 2,
        "task_timeout": 123,
    }
    assert len(selection["config_ids"]) == 2
    for index, (path, profile) in enumerate(zip(paths, profiles)):
        assert "subagent_orchestrator" not in profile
        assert "subagent_orchestrator" not in json.loads(
            path.read_text(encoding="utf-8-sig")
        )
        assert profile["agent"]["config"]["model"]["provider_id"] == f"model-{index}"
        assert profile["agent"]["config"]["subagents"] == selection

    save = AgentConfigStore.save

    async def fail_second(store, record):
        if record.name == "researcher":
            raise RuntimeError("disk failure")
        return await save(store, record)

    with monkeypatch.context() as patch:
        patch.setattr(AgentConfigStore, "save", fail_second)
        with pytest.raises(RuntimeError, match="disk failure"):
            await migrate_agent_configs(env.db, profiles)
    assert pending.exists()
    records = await env.agent_configs.list()
    assert len(records) == 1
    record = records[0]
    assert record.config == {
        "model": {"provider_id": ""},
        "persona": {"persona_id": ""},
    }
    record.name = "User edit"
    await env.agent_configs.save(record)

    # A profile first loaded after a failed import still sees the shared source.
    late = profile_path / "abconf_b.json"
    late.write_text(json.dumps({"config_version": 4}), encoding="utf-8")
    paths.append(late)
    profiles = [AstrBotConfig(str(path)) for path in paths]
    assert profiles[-1]["agent"]["config"]["subagents"] == selection
    await migrate_agent_configs(env.db, profiles)
    assert all(
        not path.with_suffix(".subagents-migration.json").exists() for path in paths
    )
    assert (await env.agent_configs.get(record.config_id)).name == "User edit"
    assert {item.config_id for item in await env.agent_configs.list()} == set(
        selection["config_ids"]
    )
    await migrate_agent_configs(env.db, [AstrBotConfig(str(path)) for path in paths])
    assert len(await env.agent_configs.list()) == 2


@pytest.mark.asyncio
async def test_config_migration_retries_failed_source_cleanup(
    environment, monkeypatch, tmp_path
):
    path = tmp_path / "cmd_config.json"
    path.write_text(
        json.dumps({"subagent_orchestrator": {"agents": [{"name": "planner"}]}}),
        encoding="utf-8",
    )
    profile = AstrBotConfig(str(path))
    pending = path.with_suffix(".subagents-migration.json")
    unlink = Path.unlink

    def fail_cleanup(current, *args, **kwargs):
        if current == pending:
            raise PermissionError("cleanup failure")
        return unlink(current, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_cleanup)
        with pytest.raises(PermissionError, match="cleanup failure"):
            await migrate_agent_configs(environment.db, [profile])
    assert pending.exists()
    await migrate_agent_configs(environment.db, [AstrBotConfig(str(path))])
    assert not pending.exists()
    assert len(await environment.agent_configs.list()) == 1


def test_failed_migration_staging_does_not_rewrite_original_config(
    tmp_path, monkeypatch
):
    path = tmp_path / "cmd_config.json"
    original = json.dumps({"subagent_orchestrator": {"agents": [{"name": "planner"}]}})
    path.write_text(original, encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(
            "astrbot.core.utils.migra_helper.os.fsync",
            Mock(side_effect=OSError("disk failure")),
        )
        with pytest.raises(OSError, match="disk failure"):
            AstrBotConfig(str(path))
    assert path.read_text(encoding="utf-8") == original
    assert not path.with_suffix(".subagents-migration.json").exists()
    assert not list(tmp_path.glob("*.tmp"))
    AstrBotConfig(str(path))
    assert path.with_suffix(".subagents-migration.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("specialized", [False, True])
async def test_native_workers_inherit_main_execution_settings(
    environment, specialized, monkeypatch
):
    env = environment

    profile = env.context.get_config()
    profile["agent"] = normalize_agent(
        {
            "runtime": "astrbot",
            "config": {
                "subagents": env.config,
                "model": {"request_max_retries": 2},
                "persona": {"persona_id": "", "system_prompt": "Parent instructions"},
                "misc": {"max_steps": 17, "tool_call_timeout": 7},
                "compression": {"max_turns": 11, "trim_turns": 3},
            },
        }
    )
    env.context.get_config = lambda **kwargs: profile
    env.context.persona_manager.get_persona_v3_by_id.return_value = {
        "prompt": "Specialist instructions",
        "tools": [],
    }
    selected = await env.save_agent(
        "Specialist", persona_id="specialist", provider_id="alternate"
    )
    from astrbot.core.astr_agent_runtime import delegated_session

    create_runner = AsyncMock(wraps=delegated_session.create_native_runner)
    monkeypatch.setattr(delegated_session, "create_native_runner", create_runner)
    agent = await env.native.spawn_agent(
        env.root,
        [{"type": "plain", "text": "Task"}],
        config_id=selected.config_id if specialized else None,
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    _, _, request, config, _ = create_runner.call_args.args
    assert config.max_steps == 17
    assert config.request_max_retries == 2
    assert config.tool_call_timeout == 7
    assert config.max_context_length == 11
    assert config.dequeue_context_length == 3
    assert env.context.provider_manager.get_provider_by_id.call_args.args == (
        ("alternate" if specialized else "model"),
    )
    assert (
        "Specialist instructions" if specialized else "Parent instructions"
    ) in request.system_prompt


@pytest.mark.asyncio
async def test_generic_worker_runs_on_the_spawning_requests_provider(environment):
    env = environment
    # ChatUI picked "alternate" for this message; the session default is "model".
    env.event.set_extra("selected_provider", "alternate")
    agent = await env.native.spawn_agent(env.root, [{"type": "plain", "text": "Task"}])
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert env.context.provider_manager.get_provider_by_id.call_args.args == (
        "alternate",
    )


class _Profile(dict):
    """A stored profile that counts its saves."""

    saves = 0

    async def save_config_async(self):
        self.saves += 1
        return True


def _stored_profile(env):
    """Route the session to a stored profile the runtime may update."""
    profile = _Profile(
        agent={"runtime": "astrbot", "config": {"subagents": env.config}}
    )
    env.context.astrbot_config_mgr = SimpleNamespace(
        confs={"chatui": profile},
        get_conf_info=lambda umo: {"id": "chatui"},
        default_conf=None,
    )
    env.context.get_config = lambda **kwargs: profile
    return profile


async def _spawn(env, **kwargs):
    agent = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Task"}], **kwargs
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    return agent


@pytest.mark.asyncio
async def test_spawn_provider_id_creates_and_selects_one_agent_config(environment):
    env = environment
    profile = _stored_profile(env)
    agent = await _spawn(env, provider_id="alternate")
    created = agent["agent_config"]
    assert created["created"] is True
    assert created["name"] == "test-model worker"
    stored = await env.agent_configs.get(created["config_id"])
    assert stored.runtime == "astrbot"
    assert stored.config == {
        "model": {"provider_id": "alternate"},
        "persona": {"persona_id": ""},
    }
    assert env.config["config_ids"] == [created["config_id"]]
    assert profile.saves == 1
    assert env.context.provider_manager.get_provider_by_id.call_args.args == (
        "alternate",
    )
    # The session panel shows the config name as the agent name.
    assert env.store.agents[agent["agent_id"]].name == "test-model worker"
    # The next request for the same model reuses it without saving again.
    again = await _spawn(env, provider_id="alternate")
    assert again["agent_config"] == {**created, "created": False}
    assert len(await env.agent_configs.list()) == 1
    assert profile.saves == 1


@pytest.mark.asyncio
async def test_spawn_provider_id_reuses_a_selected_plain_agent(environment):
    env = environment
    _stored_profile(env)
    persona = await env.save_agent(
        "Writer", persona_id="writer", provider_id="alternate"
    )
    plain = await env.save_agent("Alternate worker", provider_id="alternate")
    agent = await _spawn(env, provider_id="alternate")
    # The persona agent would surprise the user; the plain one matches.
    assert agent["agent_config"]["config_id"] == plain.config_id
    assert agent["agent_config"]["created"] is False
    assert env.config["config_ids"] == [persona.config_id, plain.config_id]


@pytest.mark.asyncio
async def test_concurrent_spawns_for_one_provider_create_one_config(environment):
    env = environment
    profile = _stored_profile(env)
    agents = await asyncio.gather(
        *(
            env.native.spawn_agent(
                env.root,
                [{"type": "plain", "text": f"Story {index}"}],
                provider_id="alternate",
            )
            for index in range(3)
        )
    )
    await env.service.wait(env.root, [a["agent_id"] for a in agents], 2000, "all")
    assert len({a["agent_config"]["config_id"] for a in agents}) == 1
    assert [a["agent_config"]["created"] for a in agents].count(True) == 1
    assert len(await env.agent_configs.list()) == 1
    assert len(env.config["config_ids"]) == 1
    assert profile.saves == 1


@pytest.mark.asyncio
async def test_spawn_provider_id_rejects_unknown_providers(environment):
    env = environment
    _stored_profile(env)
    # A disabled provider is not loaded, so it is unknown here as well.
    with pytest.raises(ValueError, match=r"Unknown.*luna.*\['model', 'alternate'\]"):
        await _spawn(env, provider_id="luna")
    spec = await env.save_agent("Worker", provider_id="model")
    with pytest.raises(ValueError, match="Send only config_id"):
        await _spawn(env, config_id=spec.config_id, provider_id="alternate")
    assert len(await env.agent_configs.list()) == 1
    assert env.config["config_ids"] == [spec.config_id]


@pytest.mark.asyncio
async def test_catalog_names_each_agents_model_and_the_chat_providers(environment):
    env = environment
    fixed = await env.save_agent("Fixed", provider_id="alternate")
    inherit = await env.save_agent("Inherit")
    env.event.set_extra("selected_provider", "model")
    request = ProviderRequest(conversation=env.conversation)
    await apply_subagents(request, env.context, env.event, runtime=env.native)
    prompt = request.system_prompt
    catalog = json.loads(
        prompt.split("<agent_configs>\n")[1].split("\n</agent_configs>")[0]
    )
    by_id = {entry["config_id"]: entry for entry in catalog}
    assert by_id[fixed.config_id]["provider_id"] == "alternate"
    assert by_id[inherit.config_id]["provider_id"] == "model"
    assert by_id[fixed.config_id]["model"] == "test-model"
    providers = json.loads(
        prompt.split("<chat_providers>\n")[1].split("\n</chat_providers>")[0]
    )
    assert [item["provider_id"] for item in providers] == ["model", "alternate"]
    schema = request.func_tool.get_tool("spawn_agent").parameters
    assert "provider_id" in schema["properties"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config_id", "provider_id", "runs_on"),
    [
        # Argument shapes logged from a model that fills every optional field.
        ("alternate", "alternate", "alternate"),
        (" ", " ", None),
        (" ", "alternate", "alternate"),
        ("alternate", None, "alternate"),
        ("", "", None),
    ],
)
async def test_spawn_ignores_blank_and_misplaced_arguments(
    environment, config_id, provider_id, runs_on
):
    env = environment
    _stored_profile(env)
    agent = await _spawn(env, config_id=config_id, provider_id=provider_id, name=" ")
    if runs_on is None:
        # A generic worker on the request's model, as without the arguments.
        assert "agent_config" not in agent
        expected = "model"
    else:
        assert agent["agent_config"]["name"] == "test-model worker"
        expected = runs_on
    assert env.context.provider_manager.get_provider_by_id.call_args.args == (expected,)
    assert env.store.agents[agent["agent_id"]].name.strip()


@pytest.mark.asyncio
async def test_spawn_rejects_only_a_real_config_provider_conflict(environment):
    env = environment
    _stored_profile(env)
    spec = await env.save_agent("Alternate", provider_id="alternate")
    agent = await _spawn(env, config_id=spec.config_id, provider_id="alternate")
    assert "agent_config" not in agent
    other = await env.save_agent("Default", provider_id="model")
    with pytest.raises(ValueError, match="Send only config_id=.*or only provider_id"):
        await _spawn(env, config_id=other.config_id, provider_id="alternate")


@pytest.mark.asyncio
async def test_spawn_provider_id_selects_an_existing_plain_agent_instead_of_creating(
    environment,
):
    env = environment
    profile = _stored_profile(env)
    existing = await env.save_agent("My alternate", provider_id="alternate")
    env.config["config_ids"].remove(existing.config_id)
    agent = await _spawn(env, provider_id="alternate")
    assert agent["agent_config"] == {
        "config_id": existing.config_id,
        "name": "My alternate",
        "created": False,
    }
    assert env.config["config_ids"] == [existing.config_id]
    assert len(await env.agent_configs.list()) == 1
    assert profile.saves == 1
