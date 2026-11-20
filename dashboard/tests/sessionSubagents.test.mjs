import assert from "node:assert/strict";
import test from "node:test";
import { ref, nextTick, reactive } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

function harness() {
  const requests = [],
    polls = new Map(),
    clocks = new Map();
  let id = 0;
  const api = loadSource(
    new URL("../src/composables/useSessionSubagents.ts", import.meta.url),
    {
      "@/utils/toolKinds": loadSource(
        new URL("../src/utils/toolKinds.ts", import.meta.url),
      ),
      "@/api/v1": {
        chatApi: {
          listSubagents: (session) =>
            new Promise((resolve, reject) =>
              requests.push({ session, resolve, reject }),
            ),
        },
      },
    },
    {
      setTimeout: (fn) => {
        polls.set(++id, fn);
        return id;
      },
      clearTimeout: (id) => polls.delete(id),
      setInterval: (fn) => {
        clocks.set(++id, fn);
        return id;
      },
      clearInterval: (id) => clocks.delete(id),
    },
  );
  const session = ref("one"),
    running = ref(false);
  const mounted = mountSetup({
    setup() {
      api.useSessionSubagentsPolling(session, running);
      return {};
    },
  });
  const flush = async () => {
    await Promise.resolve();
    await nextTick();
  };
  const reply = async (index, agents = []) => {
    requests[index].resolve({
      data: { status: "ok", data: { enabled: true, agents } },
    });
    await flush();
  };
  return {
    api,
    store: api.useSessionSubagents(),
    session,
    running,
    requests,
    polls,
    clocks,
    reply,
    flush,
    stop: mounted.stop,
  };
}

test("manual reload keeps polling while the parent turn is running", async () => {
  const h = harness();
  try {
    await h.reply(0);
    h.running.value = true;
    await nextTick();
    await h.reply(1);
    const reloaded = h.store.reload();
    await h.reply(2);
    await reloaded;
    assert.equal(h.polls.size, 1);
  } finally { h.stop(); }
});

test("elapsed clock uses the server time anchor instead of browser wall time", async () => {
  const h = harness();
  try {
    h.requests[0].resolve({ data: { status: "ok", data: { enabled: true, server_time: 100,
      agents: [{ agent_id: "a", state: "running", started_at: 90 }] } } });
    await h.flush();
    assert.equal(h.api.subagentElapsed(h.store.agents.value[0], h.store.now.value), 10);
  } finally { h.stop(); }
});

test("cancel failure survives a successful list refresh and clears on session change", async () => {
  const h = harness();
  const component = loadSource(new URL("../src/components/chat/SessionSubagents.vue", import.meta.url), {
    "@/api/v1": { chatApi: { cancelSubagent: async () => ({ data: { status: "error", message: "Cannot stop" } }) } },
    "@/composables/useSessionSubagents": h.api,
    "@/components/chat/SubagentStar.vue": {},
    "@/i18n/composables": { useModuleI18n: () => ({ tm: key => key }) },
    "@/utils/confirmDialog": { useConfirmDialog: () => ({}), askForConfirmation: async () => true },
    "@/utils/providerMetadata": { formatTokenCount: String },
  }).default;
  const props = reactive({ sessionId: "one" });
  const panel = mountSetup({ setup: (_, context) => component.setup(props, context) });
  try {
    await h.reply(0);
    const cancelled = panel.state.cancel({ agent_id: "a", name: "worker" });
    await new Promise(resolve => setImmediate(resolve));
    await h.reply(1);
    await cancelled;
    assert.equal(panel.state.cancelError, "Cannot stop");
    props.sessionId = "two";
    await nextTick();
    assert.equal(panel.state.cancelError, "");
  } finally { panel.stop(); h.stop(); }
});

test("chip focus highlight clears after its brief announcement", async () => {
  const h = harness();
  const timers = new Map();
  const component = loadSource(new URL("../src/components/chat/SessionSubagents.vue", import.meta.url), {
    "@/api/v1": { chatApi: {} }, "@/composables/useSessionSubagents": h.api,
    "@/components/chat/SubagentStar.vue": {},
    "@/i18n/composables": { useModuleI18n: () => ({ tm: key => key }) },
    "@/utils/confirmDialog": { useConfirmDialog: () => ({}) },
    "@/utils/providerMetadata": { formatTokenCount: String },
  }, { setTimeout: fn => { timers.set(fn, fn); return fn; }, clearTimeout: id => timers.delete(id) }).default;
  const panel = mountSetup(component, { sessionId: "one" });
  try {
    await h.reply(0, [{ agent_id: "a", state: "completed" }]);
    h.store.focusAgentId.value = "a";
    await nextTick();
    await nextTick();
    assert.equal(panel.state.expanded, "a");
    assert.equal(timers.size, 1);
    [...timers.values()][0]();
    await nextTick();
    assert.equal(h.store.focusAgentId.value, "");
  } finally { panel.stop(); h.stop(); }
});

test("subagent labels, task names, activities, frozen elapsed time and results", () => {
  const h = harness(),
    a = h.api;
  try {
    // One rule for every provider: no vendor, family prefix or version.
    for (const [model, expected] of [
      ["vendor/claude-haiku-5-5", "haiku"],
      ["openai/gpt-6-luna", "luna"],
      ["gemini-3.1-pro", "pro"],
      ["deepseek-v3.2", "deepseek-v3.2"],
      ["qwen3-max", "qwen3-max"],
    ]) {
      assert.equal(a.subagentModelName({ model }), expected, model);
    }
    // The model or config name is shown once, not again in the task name.
    for (const [agent, expected] of [
      [{ name: "luna-火星农场", model: "gpt-6-luna" }, "火星农场"],
      [{ name: "Luna 中国队长", model: "openai/gpt-6-luna" }, "中国队长"],
      [{ name: "gpt-6-luna: 雨夜书店", model: "gpt-6-luna" }, "雨夜书店"],
      [
        {
          name: "gpt-6-luna worker 灯塔",
          config_name: "gpt-6-luna worker",
          model: "gpt-6-luna",
        },
        "灯塔",
      ],
      // Not a prefix followed by a separator: kept as is.
      [{ name: "lunar base", model: "gpt-6-luna" }, "lunar base"],
      [{ name: "luna", model: "gpt-6-luna", task: "Write a story" }, "Write a story"],
    ]) {
      assert.equal(a.subagentTaskName(agent), expected, agent.name);
    }
    assert.equal(a.subagentIdentity({ name: "fallback" }), "fallback");
    assert.equal(
      a.subagentTaskName({
        name: "haiku-worker: task",
        config_name: "haiku-worker",
      }),
      "task",
    );
    assert.equal(
      a.subagentTaskName({ name: "worker", task: "\n First task\nSecond" }),
      "First task",
    );
    assert.equal(
      a.subagentTaskName({ name: "abcdefghijklmnopq" }),
      "abcdefghijklmno…",
    );
    for (const [state, expected] of [
      ["pending", "queued"],
      ["completed", "done"],
      ["cancelled", "stopped"],
      ["failed", "failed"],
      ["timed_out", "failed"],
      ["interrupted", "failed"],
      ["running", "thinking"],
    ]) {
      assert.equal(a.subagentActivity({ state }), expected);
      assert.equal(
        a.isSubagentActive({ state }),
        ["pending", "running"].includes(state),
      );
    }
    for (const [tool, expected] of [
      ["astrbot_execute_python", "code"],
      ["astrbot_execute_ipython", "code"],
      ["astrbot_execute_shell", "command"],
      ["astrbot_file_write_tool", "edit"],
      ["astrbot_file_edit_tool", "edit"],
      ["astrbot_grep_tool", "view"],
      ["astrbot_file_read_tool", "view"],
      ["browser_click", "computer"],
      ["computer_use", "computer"],
      ["screen_capture", "computer"],
      ["web_search", "search"],
      ["spawn_agent", "tool"],
      ["unknown", "tool"],
    ])
      assert.equal(
        a.subagentActivity({ state: "running", current_tool: tool }),
        expected,
      );
    assert.equal(
      a.subagentElapsed({ started_at: 10, finished_at: 25 }, 100),
      15,
    );
    assert.equal(a.subagentElapsed({ started_at: 10 }, 5), 0);
    assert.equal(a.subagentElapsed({}, 100), null);
    assert.equal(a.formatElapsed(65), "1:05");
    assert.equal(a.formatElapsed(4), "0:04");
    const results = [
      JSON.stringify({ agent_id: "a" }),
      { agent_id: "b" },
      "invalid",
      null,
    ];
    assert.deepEqual(
      Array.from(
        a.spawnedAgentIds([
          {
            type: "tool_call",
            tool_calls: results.map((result) => ({
              name: "spawn_agent",
              result,
            })),
          },
        ]),
      ),
      ["a", "b"],
    );
    assert.equal(a.spawnedAgentIds(null).length, 0);
  } finally {
    h.stop();
  }
});

test("polling and elapsed clock stop when idle and on unmount", async () => {
  const h = harness();
  try {
    await h.reply(0, [{ agent_id: "a", state: "running" }]);
    assert.equal(h.polls.size, 1);
    assert.equal(h.clocks.size, 1);
    const [id, poll] = [...h.polls][0];
    h.polls.delete(id);
    poll();
    await h.reply(1, [{ agent_id: "a", state: "completed" }]);
    assert.equal(h.polls.size, 0);
    assert.equal(h.clocks.size, 0);
    h.running.value = true;
    await nextTick();
    await h.reply(2);
    assert.equal(h.polls.size, 1);
  } finally {
    h.stop();
  }
  assert.equal(h.polls.size, 0);
  assert.equal(h.clocks.size, 0);
});

test("stale success and failure cannot replace the current session state", async () => {
  const h = harness();
  try {
    h.session.value = "two";
    await nextTick();
    await h.reply(1, [{ agent_id: "two", state: "completed" }]);
    h.requests[0].reject(new Error("old request failed"));
    await h.flush();
    assert.equal(h.store.error.value, "");
    assert.equal(h.store.agents.value[0].agent_id, "two");
    h.session.value = "three";
    await nextTick();
    h.session.value = "four";
    await nextTick();
    await h.reply(3);
    await h.reply(2, [{ agent_id: "old", state: "running" }]);
    assert.equal(h.store.agents.value.length, 0);
    assert.equal(h.polls.size, 0);
  } finally {
    h.stop();
  }
});

test("an older running request cannot restart polling after the turn stops", async () => {
  const h = harness();
  try {
    await h.reply(0);
    h.running.value = true;
    await nextTick();
    h.running.value = false;
    await nextTick();
    await h.reply(2);
    await h.reply(1);
    assert.equal(h.polls.size, 0);
  } finally {
    h.stop();
  }
});

test("switching sessions immediately stops the previous elapsed clock", async () => {
  const h = harness();
  try {
    await h.reply(0, [{ state: "running" }]);
    h.session.value = null;
    await nextTick();
    assert.equal(h.clocks.size, 0);
    assert.equal(h.polls.size, 0);
  } finally {
    h.stop();
  }
});
