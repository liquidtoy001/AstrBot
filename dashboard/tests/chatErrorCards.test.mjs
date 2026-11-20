import assert from "node:assert/strict";
import test from "node:test";
import { h } from "vue";
import { loadSource, mountTemplate } from "./helpers/vueHarness.mjs";

const ChatErrorCard = loadSource(
  new URL(
    "../src/components/chat/message_list_comps/ChatErrorCard.vue",
    import.meta.url,
  ),
  { "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) } },
  {},
  true,
).default;

function mountCard(code) {
  const emitted = [];
  const card = mountTemplate({
    render: () =>
      h(ChatErrorCard, {
        code,
        message: "detail",
        onConfigureModels: () => emitted.push("configureModels"),
      }),
  });
  const text = () =>
    card
      .findAll((node) => Boolean(node.text))
      .map((node) => node.text)
      .join(" ");
  const button = () => card.findAll((node) => node.type === "button")[0];
  return { card, emitted, text, button };
}

for (const [code, category, configurable] of [
  // Codes from classify_provider_failure.
  ["providerAuth", "apiKey", true],
  ["providerToolsRequireResponses", "responsesApi", true],
  ["providerModelNotFound", "modelNotFound", true],
  ["providerRateLimit", "rateLimit", false],
  // Upstream codes keep their cards.
  ["noProvider", "noModel", true],
  ["providerNotFound", "modelConfiguration", true],
  ["connection_error", "connection", false],
  ["provider_error", "generic", false],
]) {
  test(`${code} shows the ${category} card`, () => {
    const { card, emitted, text, button } = mountCard(code);
    try {
      assert.match(text(), new RegExp(`executionError\\.${category}\\.title`));
      assert.match(
        text(),
        new RegExp(`executionError\\.${category}\\.description`),
      );
      if (configurable) {
        // The action opens the model configuration (Chat.vue: openProviderWorkspace).
        assert.match(text(), /executionError\.configureModels/);
        button().props.onClick();
        assert.deepEqual(emitted, ["configureModels"]);
      } else {
        assert.equal(button(), undefined);
      }
    } finally {
      card.stop();
    }
  });
}
