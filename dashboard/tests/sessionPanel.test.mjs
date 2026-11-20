import assert from "node:assert/strict";
import test from "node:test";
import { nextTick, reactive } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

function mountPanel(overrides = {}, api = {}, storage = new Map()) {
  // Per-conversation options as the shared store keeps them.
  const prefs = {};
  const component = loadSource(
    new URL("../src/components/chat/SessionPanel.vue", import.meta.url),
    {
      "@/components/chat/chatPanelTransition.css": {},
      "@/api/v1": {
        chatApi: {
          getSessionSettings: async () => ({
            data: { status: "ok", data: { persona: { conversation: "new" } } },
          }),
          ...api,
        },
      },
      "@/components/shared/StyledMenu.vue": {},
      "@/components/chat/SessionSubagents.vue": {},
      "@/i18n/composables": {
        useModuleI18n: () => ({
          tm: (key, params) => (params ? `${key}:${JSON.stringify(params)}` : key),
        }),
      },
      "@/utils/providerMetadata": { formatTokenCount: String },
      "@/utils/chatSessionPrefs.mjs": {
        readChatSessionPrefs: (sessionId) => ({ ...prefs[sessionId] }),
        writeChatSessionPref: (sessionId, key, value) => {
          prefs[sessionId] = { ...prefs[sessionId], [key]: value };
          if (value === null) delete prefs[sessionId][key];
        },
      },
    },
    {
      localStorage: {
        getItem: (key) => storage.get(key) ?? null,
        setItem: (key, value) => storage.set(key, value),
      },
    },
  ).default;
  const props = reactive({
    modelValue: true,
    messages: [],
    used: 0,
    limit: 0,
    sessionId: "one",
    ...overrides,
  });
  const mounted = mountSetup({
    setup: (_, ctx) => component.setup(props, { ...ctx, emit() {} }),
  });
  return { props, state: mounted.state, stop: mounted.stop, prefs };
}

// Values from the sandboxed module are compared as plain data.
const plain = (value) => JSON.parse(JSON.stringify(value));
const stats = (breakdown) => ({ content: { agentStats: { context_breakdown: breakdown } } });

test("context rows add up to the reported usage and bound free space", () => {
  for (const used of [1, 2, 5, 100, 101]) {
    const panel = mountPanel({ used, messages: [stats({ system: 1, tools: 1, messages: 1 })] });
    const rows = panel.state.rows;
    assert.equal(rows.reduce((sum, row) => sum + row.tokens, 0), used);
    assert.ok(rows.every((row) => row.tokens >= 0));
    panel.stop();
  }
  const panel = mountPanel({ used: 10, limit: 8, messages: [stats({ system: 0, messages: 4 })] });
  assert.deepEqual(
    plain(panel.state.rows.map(({ key, tokens }) => [key, tokens])),
    [["messages", 10], ["free", 0]],
  );
  panel.props.limit = 0;
  assert.deepEqual(plain(panel.state.rows.map((row) => row.key)), ["messages"]);
  panel.stop();
});

test("percentages show <0.1% for tiny shares and - without a limit", () => {
  const panel = mountPanel({ limit: 10000 });
  assert.equal(panel.state.percent(1), "<0.1%");
  panel.props.limit = 3;
  assert.equal(panel.state.percent(1), "33.3%");
  panel.props.limit = 0;
  assert.equal(panel.state.percent(1), "-");
  panel.stop();
});

test("thresholds round to thousands, stay unique and mark immediate levels", async () => {
  const panel = mountPanel({ limit: 111111, used: 44000 });
  assert.equal(panel.state.triggerTokens, 91111);
  assert.deepEqual(
    plain(panel.state.thresholdOptions.map((option) => [option.value, option.immediate])),
    [[0, false], [56000, false], [44000, true], [33000, true]],
  );
  panel.state.setThreshold(120000);
  panel.props.limit = 100000;
  assert.equal(panel.state.triggerTokens, 100000);
  assert.equal(panel.prefs.one.compact_threshold, 120000);
  panel.props.used = 100000;
  assert.equal(panel.state.nearCompaction, false);
  panel.props.used = 100001;
  assert.equal(panel.state.nearCompaction, true);
  panel.state.setThreshold(0);
  assert.equal("compact_threshold" in panel.prefs.one, false);
  // Each conversation reads its own stored threshold.
  panel.prefs.two = { compact_threshold: 50000 };
  panel.props.sessionId = "two";
  await nextTick();
  assert.equal(panel.state.threshold, 50000);
  for (const limit of [0, 500, 1000, 1249, 1250, 2000]) {
    panel.props.limit = limit;
    const values = panel.state.thresholdOptions.map((option) => option.value);
    assert.equal(new Set(values).size, values.length);
    assert.equal(values.filter((value) => value === 0).length, 1);
    assert.ok(values.every((value) => value <= limit));
  }
  panel.stop();
});

test("usage and compactions add up across replies; the newest breakdown wins", () => {
  const reply = (n) => ({
    content: {
      agentStats: {
        token_usage: { input_other: 10, input_cached: 5, output: n },
        compactions: n,
        context_breakdown: { messages: n },
      },
    },
  });
  const panel = mountPanel({ messages: [{}, reply(1), reply(2)] });
  assert.deepEqual(plain(panel.state.stats), {
    usage: { input: 30, cached: 10, output: 3 },
    compactions: 3,
    breakdown: { messages: 2 },
  });
  panel.props.messages = [];
  assert.deepEqual(plain(panel.state.stats), {
    usage: { input: 0, cached: 0, output: 0 },
    compactions: 0,
    breakdown: null,
  });
  panel.stop();
});

for (const method of ["compactNow", "setPersona"]) {
  for (const fail of [false, true]) {
    test(`${method} ignores a stale ${fail ? "failure" : "success"}`, async () => {
      let settle;
      const pending = () =>
        new Promise((resolve, reject) => {
          settle = () =>
            fail
              ? reject(new Error("old error"))
              : resolve({
                  data: {
                    status: "ok",
                    data: { before: 10, after: 5, persona: { conversation: "old" } },
                  },
                });
        });
      const panel = mountPanel({}, { compactSession: pending, setSessionPersona: pending });
      try {
        await new Promise((resolve) => setImmediate(resolve));
        const request = panel.state[method]("old");
        panel.props.sessionId = "two";
        await nextTick();
        await new Promise((resolve) => setImmediate(resolve));
        settle();
        await request;
        assert.equal(panel.state.settings.persona.conversation, "new");
        assert.equal(panel.state.compactMessage, "");
        assert.equal(panel.state.personaError, "");
        assert.equal(panel.state.compacting, false);
        assert.equal(panel.state.personaSaving, false);
      } finally {
        panel.stop();
      }
    });
  }
}

test("file changes add up per path and skip undone and pathless changes", () => {
  const call = (file_change) => ({ file_change });
  const messages = [
    {},
    {
      content: {
        message: [
          { type: "plain", text: "done" },
          {
            type: "tool_call",
            tool_calls: [
              call({ path: "a", added_count: 2 }),
              call({ path: "a", removed_count: 1 }),
              call({ path: "b" }),
              call({ added_count: 100 }),
              call({ path: "c", added_count: 5, undone: true }),
              call({ path: "d", added_count: 7, change_id: "x1" }),
              {},
            ],
          },
        ],
      },
    },
  ];
  const storage = new Map([["chat.undoneFileChanges", JSON.stringify(["x1"])]]);
  const panel = mountPanel({ messages }, {}, storage);
  assert.deepEqual(plain(panel.state.fileChanges), [
    { path: "a", added: 2, removed: 1 },
    { path: "b", added: 0, removed: 0 },
  ]);
  assert.deepEqual(plain(panel.state.changeTotals), { added: 2, removed: 1 });
  // Without previews (no file change tracking) the section has nothing.
  panel.props.messages = [{ content: { message: [{ type: "tool_call", tool_calls: [{}] }] } }];
  assert.deepEqual(plain(panel.state.fileChanges), []);
  panel.stop();
});
