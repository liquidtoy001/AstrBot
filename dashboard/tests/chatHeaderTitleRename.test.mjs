import assert from "node:assert/strict";
import test from "node:test";
import * as pinia from "pinia";
import { loadSource, mountTemplate } from "./helpers/vueHarness.mjs";

function loadStore() {
  pinia.setActivePinia(pinia.createPinia());
  const { useChatHeaderStore } = loadSource(
    new URL("../src/stores/chatHeader.ts", import.meta.url),
    { pinia },
  );
  return useChatHeaderStore();
}

test("a header rename request only counts while a conversation is open", () => {
  const store = loadStore();
  store.SET_CONTEXT({ title: "Project only" });
  store.REQUEST_RENAME();
  assert.equal(store.renameRequested, false);

  store.SET_CONTEXT({ title: "Chat", titleRenamable: true });
  store.REQUEST_RENAME();
  assert.equal(store.renameRequested, true);

  store.CLEAR_CONTEXT();
  assert.equal(store.titleRenamable, false);
});

test("double-clicking the header title asks for a rename", () => {
  const store = loadStore();
  store.SET_CONTEXT({ title: "Chat", titleRenamable: true });
  const component = loadSource(
    new URL("../src/components/chat/ChatToolbarContext.vue", import.meta.url),
    {
      "vue-router": {
        useRoute: () => ({ params: {}, query: {}, path: "/chat/s1" }),
        useRouter: () => ({ push() {} }),
      },
      "@lucide/vue": { ChevronDown: {} },
      "@/components/shared/StyledMenu.vue": { default: { render: () => null } },
      "@/components/chat/ProviderModelMenu.vue": { default: { render: () => null } },
      "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) },
      "@/stores/chatHeader": { useChatHeaderStore: () => store },
    },
    {},
    true,
  ).default;
  const mounted = mountTemplate(component);
  const [title] = mounted.findAll((node) => node.props.class === "chat-toolbar-context-title");
  assert.match(title.props.title, /conversation\.renameByDoubleClick/);
  title.props.onDblclick();
  assert.equal(store.renameRequested, true);
  mounted.stop();
});
