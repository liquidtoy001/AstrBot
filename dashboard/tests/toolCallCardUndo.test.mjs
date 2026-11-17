import assert from "node:assert/strict";
import test from "node:test";
import { reactive, nextTick } from "vue";
import { loadSource, mountSetup, mountTemplate } from "./helpers/vueHarness.mjs";

function setup(toolCall, api = {}, confirm = async () => false, render = false) {
  const timers = new Set();
  const component = loadSource(
    new URL(
      "../src/components/chat/message_list_comps/ToolCallCard.vue",
      import.meta.url,
    ),
    {
      "@/api/v1": { chatApi: api },
      "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) },
      "@/utils/confirmDialog": { useConfirmDialog: () => ({}), askForConfirmation: confirm },
    },
    {
      localStorage: { getItem: () => '["undone"]' },
      setInterval: (fn) => {
        timers.add(fn);
        return fn;
      },
      clearInterval: (fn) => timers.delete(fn),
    },
    render,
  ).default;
  return { ...(render ? mountTemplate : mountSetup)(component, { toolCall, initialExpanded: true }), timers };
}

test("undo waits without a spinner and a replacement card owns its busy state", async () => {
  let approve;
  const requests = [];
  const call = reactive({ file_change: { change_id: "first" } });
  const h = setup(call, { undoFileChange: () => new Promise(resolve => requests.push(resolve)) },
    () => new Promise(resolve => { approve = resolve; }));
  try {
    const first = h.state.undoFileChange();
    assert.equal(h.state.undoState.busy, false);
    approve(true);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(h.state.undoState.busy, true);
    call.file_change = { change_id: "second" };
    await nextTick();
    assert.equal(h.state.undoState.busy, false);
    const second = h.state.undoFileChange();
    approve(true);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(h.state.undoState.busy, true);
    requests[0]();
    await first;
    assert.equal(h.state.undoState.busy, true);
    requests[1]();
    await second;
    assert.equal(h.state.undoState.busy, false);
  } finally { h.stop(); }
});

test("undo display refreshes when streamed history supplies a different change", async () => {
  const call = reactive({ ts: 1, finished_ts: 2 });
  const h = setup(call);
  try {
    assert.equal(h.state.undoState.done, false);
    call.file_change = { change_id: "undone" };
    await nextTick();
    assert.equal(h.state.undoState.done, true);
    call.file_change = { change_id: "new" };
    await nextTick();
    assert.equal(h.state.undoState.done, false);
  } finally {
    h.stop();
  }
});

test("successful undo removes the rendered undo button", async () => {
  const calls = [];
  const h = setup({ file_change: { change_id: "new", undoable: true } },
    { undoFileChange: async id => calls.push(id) }, async () => true, true);
  try {
    const undo = h.findAll(n => n.type === "button" && n.children.some(c => c.text.includes("fileChange.undo")))[0];
    assert.ok(undo);
    await undo.props.onClick();
    await nextTick();
    assert.deepEqual(calls, ["new"]);
    assert.equal(h.findAll(n => n.type === "button" && n.children.some(c => c.text.includes("fileChange.undo"))).length, 0);
    assert.ok(h.findAll(n => n.text.includes("fileChange.done")).length);
  } finally { h.stop(); }
});
