import assert from "node:assert/strict";
import test from "node:test";
import { nextTick, ref } from "vue";
import { loadSource, mountSetup, mountTemplate } from "./helpers/vueHarness.mjs";

const i18n = { useModuleI18n: () => ({ tm: (key) => key }) };

function loadProviderSelectMenu(requests) {
  return loadSource(
    new URL("../src/components/shared/ProviderSelectMenu.vue", import.meta.url),
    {
      vuetify: { useDisplay: () => ({ height: ref(800) }) },
      "@/api/v1": {
        providerApi: {
          listByProviderType: () =>
            new Promise((resolve) => requests.push(resolve)),
        },
      },
      "@/components/shared/AstrBotConfig.vue": {},
      "@/components/provider/ProviderChatCompletionPanel.vue": {},
      "@/views/ProviderPage.vue": {},
      "@/i18n/composables": i18n,
      "@/utils/toast": { useToast: () => ({}) },
      "@/utils/providerMetadata": {},
      "@/composables/useProviderModelConfigDialog": {
        useProviderModelConfigDialog: () => ({}),
      },
    },
  ).default;
}

// The real ProviderSelectMenu child feeds the selected provider's type to the
// thinking level menu, as in the app.
function mountMenu(selection) {
  const requests = [];
  const childProps = {};
  const child = loadProviderSelectMenu(requests);
  const parent = loadSource(
    new URL("../src/components/chat/ProviderModelMenu.vue", import.meta.url),
    {
      "@/components/shared/ProviderSelectMenu.vue": {
        default: {
          ...child,
          render() {
            Object.assign(childProps, this.$props);
            return this.$slots.top?.();
          },
        },
      },
      "@/composables/useProviderModelSelection": {
        useProviderModelSelection: () => selection,
      },
      "@/i18n/composables": i18n,
    },
    {},
    true,
  ).default;
  return { requests, childProps, h: mountTemplate(parent) };
}

const PROVIDERS = [
  { id: "xai", model: "grok", type: "xai_chat_completion" },
  {
    id: "openai",
    model: "gpt",
    type: "openai_chat_completion",
    supports_fast_mode: true,
  },
  { id: "other", model: "x", type: "unknown_chat_completion" },
];

async function loaded(requests) {
  requests[0]({ data: { status: "ok", data: PROVIDERS } });
  await new Promise((resolve) => setImmediate(resolve));
  await nextTick();
}

function levelButtons(h) {
  return h.findAll(
    (n) => n.type === "button" && n.props.class?.includes("effort-option"),
  );
}

test("levels follow the provider type once its metadata matches the selection", async () => {
  const selection = {
    selectedProviderId: ref("xai"),
    selectedModelName: ref("grok"),
    reasoningEffort: ref("high"),
    fastMode: ref(false),
    setSelection() {},
  };
  const { requests, h } = mountMenu(selection);
  try {
    await nextTick();
    assert.equal(
      requests.length,
      1,
      "metadata loads before the menu is opened",
    );
    // Before the list arrives, a stored level is not reset against a guess.
    assert.equal(selection.reasoningEffort.value, "high");
    await loaded(requests);
    assert.equal(levelButtons(h).length, 2, "xAI offers low and high");

    selection.selectedProviderId.value = "openai";
    selection.reasoningEffort.value = "medium";
    await nextTick();
    await nextTick();
    assert.equal(selection.reasoningEffort.value, "medium");
    const buttons = levelButtons(h);
    assert.equal(buttons.length, 3);
    assert.equal(
      buttons.filter((n) => n.props["aria-pressed"] === true).length,
      1,
    );

    selection.selectedProviderId.value = "xai";
    await nextTick();
    await nextTick();
    assert.equal(
      selection.reasoningEffort.value,
      "low",
      "an unsupported level falls back to low",
    );

    selection.selectedProviderId.value = "other";
    await nextTick();
    await nextTick();
    assert.equal(
      selection.reasoningEffort.value,
      "",
      "types without a level send none",
    );
    assert.equal(levelButtons(h).length, 0);
  } finally {
    h.stop();
  }
});

test("fast mode is offered only where the backend marks the provider", async () => {
  const selection = {
    selectedProviderId: ref("openai"),
    selectedModelName: ref("gpt"),
    reasoningEffort: ref("low"),
    fastMode: ref(true),
    setSelection() {},
  };
  const { requests, h } = mountMenu(selection);
  const switches = () => h.findAll((n) => n.type === "input");
  try {
    await nextTick();
    // Before the list arrives, a stored choice is kept.
    assert.equal(switches().length, 0);
    assert.equal(selection.fastMode.value, true);
    await loaded(requests);
    assert.equal(switches().length, 1);
    assert.equal(selection.fastMode.value, true);

    // Another model picked for the same entry was not judged by the backend.
    selection.selectedModelName.value = "gpt-other";
    await nextTick();
    await nextTick();
    assert.equal(switches().length, 0);
    assert.equal(selection.fastMode.value, false, "unsupported turns it off");
    selection.selectedModelName.value = "gpt";

    selection.fastMode.value = true;
    selection.selectedProviderId.value = "xai";
    await nextTick();
    await nextTick();
    assert.equal(switches().length, 0);
    assert.equal(selection.fastMode.value, false, "unsupported turns it off");
  } finally {
    h.stop();
  }
});

test("the ChatUI model button shows only the model name", async () => {
  const selection = {
    selectedProviderId: ref("openai"),
    selectedModelName: ref("gpt"),
    reasoningEffort: ref(""),
    fastMode: ref(false),
    setSelection() {},
  };
  const { childProps, h } = mountMenu(selection);
  try {
    assert.equal(childProps.modelOnly, true);
  } finally {
    h.stop();
  }

  const requests = [];
  const menu = mountSetup(loadProviderSelectMenu(requests), {
    modelValue: "openai",
    fallbackModel: "gpt-saved",
    providerType: "chat_completion",
    variant: "header",
    modelOnly: true,
    preload: true,
  });
  try {
    // Before the provider list arrives, the saved model name is shown.
    assert.equal(menu.state.triggerTitle, "gpt-saved");
    await loaded(requests);
    assert.equal(menu.state.triggerTitle, "gpt");
    assert.equal(menu.state.selectedProvider.id, "openai");
  } finally {
    menu.stop();
  }
});
