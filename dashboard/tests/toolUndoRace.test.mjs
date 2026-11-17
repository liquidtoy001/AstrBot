import assert from "node:assert/strict";
import test from "node:test";
import { reactive, nextTick } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

function setup() {
  const confirmations = [],
    requests = [],
    storage = new Map();
  const component = loadSource(
    new URL(
      "../src/components/chat/message_list_comps/ToolCallCard.vue",
      import.meta.url,
    ),
    {
      "@/api/v1": {
        chatApi: {
          undoFileChange: (id) =>
            new Promise((resolve, reject) =>
              requests.push({ id, resolve, reject }),
            ),
        },
      },
      "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) },
      "@/utils/confirmDialog": {
        useConfirmDialog: () => ({}),
        askForConfirmation: () =>
          new Promise((resolve) => confirmations.push(resolve)),
      },
    },
    {
      localStorage: {
        getItem: (key) => storage.get(key),
        setItem: (key, value) => storage.set(key, value),
      },
    },
  ).default;
  const call = reactive({ finished_ts: 1, file_change: { change_id: "old" } });
  return {
    ...mountSetup(component, { toolCall: call }),
    call,
    requests,
    confirmations,
    storage,
  };
}

for (const success of [true, false]) {
  test(`an old undo ${
    success ? "success" : "failure"
  } cannot update a replacement card`, async () => {
    const h = setup();
    try {
      const work = h.state.undoFileChange();
      h.confirmations[0](true);
      await new Promise(setImmediate);
      assert.equal(h.requests[0].id, "old");
      h.call.file_change = { change_id: "new" };
      await nextTick();
      if (success) h.requests[0].resolve();
      else h.requests[0].reject(new Error("old failure"));
      await work;
      assert.equal(h.state.undoState.done, false);
      assert.equal(h.state.undoState.message, "");
      assert.equal(h.state.undoState.busy, false);
      if (success)
        assert.deepEqual(JSON.parse(h.storage.get("chat.undoneFileChanges")), [
          "old",
        ]);
    } finally {
      h.stop();
    }
  });
}

test("a pending confirmation cannot undo a replacement card or open twice", async () => {
  const h = setup();
  try {
    const first = h.state.undoFileChange();
    void h.state.undoFileChange();
    assert.equal(h.confirmations.length, 1);
    h.call.file_change = { change_id: "new" };
    await nextTick();
    h.confirmations[0](true);
    await first;
    assert.equal(h.requests.length, 0);
    assert.equal(h.state.undoState.busy, false);
  } finally {
    h.stop();
  }
});
