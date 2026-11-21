import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { reactive } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

function mountDialog({ routing = {}, configId = "default" } = {}) {
  const calls = [];
  const ok = (data) => ({ status: 200, data: { status: "ok", data } });
  const component = loadSource(
    new URL("../src/components/chat/ChatSettingsDialog.vue", import.meta.url),
    {
      "vue-router": { useRouter: () => ({ push: (path) => calls.push(["push", path]) }) },
      "@/api/v1": {
        chatApi: {
          getSessionSettings: async () => ok({ config_id: configId, config_name: "Main" }),
        },
        configRouteApi: {
          list: async () => ok({ routing }),
          upsert: async (umo, body) => (calls.push(["route", umo, body.config_id]), ok({})),
        },
        configProfileApi: {
          get: async (id) =>
            ok({
              config: { agent: { config: { subagents: { enabled: false } } } },
              // The profile also has the persona, context and computer use groups.
              metadata: {
                ai_group: {
                  metadata: {
                    persona: { items: {} },
                    truncate_and_compress: { items: {} },
                    subagents: { items: {} },
                    agent_computer_use: { items: {} },
                    other: {},
                  },
                },
              },
            }),
          update: async (id, config) => (calls.push(["update", id, config]), ok({})),
          create: async (body) => (calls.push(["create", body.name]), ok({ conf_id: "chatui" })),
        },
      },
      "@/components/shared/AstrBotConfigV4.vue": {},
      "@/i18n/composables": {
        useI18n: () => ({ t: (key) => key }),
        useModuleI18n: () => ({ tm: (key) => key }),
        useLanguageSwitcher: () => ({ locale: "en-US", languageOptions: [], switchLanguage() {} }),
      },
      "@/stores/customizer": { useCustomizerStore: () => ({}) },
    },
  ).default;
  const props = reactive({
    modelValue: false,
    sessionId: "s1",
    enableStreaming: true,
    enableReasoning: true,
    sendShortcut: "enter",
    transportMode: "sse",
  });
  const mounted = mountSetup({
    setup: (_, ctx) => component.setup(props, { ...ctx, emit() {} }),
  });
  return { state: mounted.state, calls, stop: mounted.stop };
}

for (const [label, routing, configId, shared] of [
  ["the default profile", {}, "default", true],
  ["a profile also routed to a bot", { "qq:group:1": "main" }, "main", true],
  ["a ChatUI-only profile", { "webchat::": "main" }, "main", false],
]) {
  test(`agent page treats ${label} as ${shared ? "shared" : "ChatUI-only"}`, async () => {
    const dialog = mountDialog({ routing, configId });
    await dialog.state.loadAgentSettings();
    assert.equal(dialog.state.agentShared, shared);
    // Only the sub-agent group is rendered; the persona group would also edit
    // the shared persona, so it stays on the config page.
    assert.deepEqual(
      JSON.parse(JSON.stringify(dialog.state.agentSections.map((section) => section.key))),
      ["subagents"],
    );
    dialog.stop();
  });
}

test("agent page saves edits through the profile API and creates a ChatUI profile", async () => {
  const dialog = mountDialog({ configId: "main" });
  await dialog.state.loadAgentSettings();
  assert.equal(dialog.state.agentDirty, false);
  dialog.state.agentConfig.agent.config.subagents.enabled = true;
  assert.equal(dialog.state.agentDirty, true);
  await dialog.state.saveAgentSettings();
  const update = dialog.calls.find((call) => call[0] === "update");
  assert.equal(update[1], "main");
  assert.equal(update[2].agent.config.subagents.enabled, true);
  assert.equal(dialog.state.agentDirty, false);
  assert.equal(dialog.state.agentStatus, "agentSettings.saved");

  await dialog.state.createChatUiProfile();
  assert.deepEqual(
    JSON.parse(JSON.stringify(dialog.calls.filter((call) => ["create", "route"].includes(call[0])))),
    [["create", "ChatUI"], ["route", "webchat::", "chatui"]],
  );
  assert.equal(dialog.state.agentStatus, "agentSettings.ownDone");
  dialog.stop();
});

test("the page is named after sub-agents in every language", () => {
  const titles = Object.fromEntries(
    ["en-US", "zh-CN", "ja-JP", "ru-RU"].map((locale) => [
      locale,
      JSON.parse(
        readFileSync(
          new URL(`../src/i18n/locales/${locale}/features/chat.json`, import.meta.url),
          "utf8",
        ).trimStart(), // drops a byte order mark
      ).agentSettings.title,
    ]),
  );
  assert.deepEqual(titles, {
    "en-US": "Subagents",
    "zh-CN": "子代理",
    "ja-JP": "サブエージェント",
    "ru-RU": "Субагенты",
  });
});
