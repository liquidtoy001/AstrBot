import assert from "node:assert/strict";
import test from "node:test";
import { ref, nextTick, watch } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

test("clicking the same agent twice triggers the focus watcher twice", async () => {
  const focusAgentId = ref("");
  const focused = [];
  const unwatch = watch(focusAgentId, (id) => {
    if (id) focused.push(id);
  });
  const component = loadSource(
    new URL(
      "../src/components/chat/message_list_comps/SubagentChips.vue",
      import.meta.url,
    ),
    {
      "@/composables/useSessionSubagents": {
        useSessionSubagents: () => ({ byId: ref(new Map()), focusAgentId }),
      },
      "@/components/chat/SubagentStar.vue": {},
      "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) },
      "@/stores/chatHeader": {
        useChatHeaderStore: () => ({ SET_SESSION_PANEL_OPEN() {} }),
      },
    },
  ).default;
  const mounted = mountSetup(component, { agentIds: [] });
  try {
    await mounted.state.openAgent("a1");
    await nextTick();
    await mounted.state.openAgent("a1");
    await nextTick();
    // Removing B10's tick collapses both assignments and loses the second focus.
    assert.deepEqual(focused, ["a1", "a1"]);
  } finally {
    mounted.stop();
    unwatch();
  }
});

test("each sub-agent star keeps one color derived from its agent id", () => {
  const composable = loadSource(
    new URL("../src/composables/useSessionSubagents.ts", import.meta.url),
    { "@/utils/toolKinds": { TOOL_KINDS: {} }, "@/api/v1": { chatApi: {} } },
  );
  const component = loadSource(
    new URL("../src/components/chat/SubagentStar.vue", import.meta.url),
    { "@/composables/useSessionSubagents": composable },
  ).default;
  const colorOf = (agentId) => {
    const mounted = mountSetup(component, { agentId });
    try {
      return mounted.state.color;
    } finally {
      mounted.stop();
    }
  };
  // The chip and the panel row mount separately; both must get the same color.
  assert.deepEqual(colorOf("subagent-7f3a"), colorOf("subagent-7f3a"));
  const colors = new Set(
    ["a1", "a2", "a3", "a4", "a5", "b1", "b2", "b3"].map(
      (id) => colorOf(id).light,
    ),
  );
  assert.ok(colors.size >= 3, [...colors].join(","));
  // None may repeat the blue or gold of the reply avatar's star.
  const avatar = ["#2f86bd", "#4aa3dc", "#f5a623", "#ffe08a"];
  for (let i = 0; i < 64; i++) {
    const { light, dark } = colorOf(`agent-${i}`);
    assert.ok(!avatar.includes(light) && !avatar.includes(dark), light);
  }
  for (const id of ["a1", "b2"]) {
    const { light, dark } = colorOf(id);
    assert.match(light, /^#[0-9a-f]{6}$/);
    assert.notEqual(light, dark);
  }
});
