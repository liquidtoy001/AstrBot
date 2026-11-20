import assert from "node:assert/strict";
import test from "node:test";
import { nextTick, ref } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

// The session view is a built-in workbench tab: it opens in place of the
// launcher, survives a reload with the conversation's layout, and opens once.
function workbench(saved) {
  const writes = [];
  const store = saved || { global: {}, sessions: {} };
  const { useChatWorkbench } = loadSource(
    new URL("../src/composables/useChatWorkbench.ts", import.meta.url),
    {
      "@/utils/chatViews": { workbenchKey: Symbol("workbench") },
      "@/utils/chatPreferences": {
        chatPreferences(update) {
          if (update) {
            update(store);
            writes.push(JSON.parse(JSON.stringify(store)));
          }
          return store;
        },
      },
      "@/utils/chatConfigBinding": {
        getStoredDashboardUsername: () => "alice",
      },
    },
  );
  const sessionId = ref("s1");
  const mounted = mountSetup({ setup: () => useChatWorkbench(sessionId) });
  return { ...mounted, store, writes };
}

test("the session view opens as one built-in tab in place of the launcher", async () => {
  const h = workbench();
  try {
    h.state.openPage();
    h.state.openBuiltin("session");
    h.state.openBuiltin("session");
    const current = h.state.state;
    assert.deepEqual(
      JSON.parse(
        JSON.stringify(
          current.tabs.map((tab) => [
            tab.part.id,
            tab.builtin,
            Boolean(tab.launcher),
          ]),
        ),
      ),
      [["builtin:session", "session", false]],
    );
    assert.equal(current.activeId, "builtin:session");
    assert.equal(current.open, true);
    await nextTick();
    assert.deepEqual(
      JSON.parse(JSON.stringify(h.store.sessions.s1.workbench.tabs)),
      [{ id: "builtin:session", name: "", title: "", builtin: "session" }],
    );
  } finally {
    h.stop();
  }
});

test("a saved session tab is restored after a reload", () => {
  const h = workbench({
    global: {},
    sessions: {
      s1: {
        workbench: {
          tabs: [{ id: "builtin:session", builtin: "session" }],
          activeId: "builtin:session",
          open: true,
        },
      },
    },
  });
  try {
    const tab = h.state.state.tabs[0];
    assert.equal(tab.builtin, "session");
    assert.equal(tab.part.id, "builtin:session");
    assert.equal(h.state.state.open, true);
  } finally {
    h.stop();
  }
});
