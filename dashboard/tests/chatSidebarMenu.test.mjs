import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import * as pinia from "pinia";
import ts from "typescript";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

const plain = (value) => JSON.parse(JSON.stringify(value));
const i18n = {
  useI18n: () => ({ t: (key) => key }),
  useModuleI18n: () => ({ tm: (key) => key }),
};

test("every toast has its own identity so the snackbar restarts its timer", () => {
  pinia.setActivePinia(pinia.createPinia());
  const { useToastStore } = loadSource(
    new URL("../src/stores/toast.js", import.meta.url),
    { pinia },
  );
  const store = useToastStore();
  // The same message twice in a row, as when a conversation is moved twice.
  store.add({ message: "Moved", color: "success" });
  store.add({ message: "Moved", color: "success" });
  const first = store.current.id;
  store.shift();
  assert.notEqual(store.current.id, first);

  // The snackbar is rebuilt per toast; one left open never times out again.
  const app = readFileSync(new URL("../src/App.vue", import.meta.url), "utf8");
  assert.match(app, /<v-snackbar[^>]*:key="toastStore\.current\.id"/);
});

test("choosing a context menu entry closes the menu and reports the entry", () => {
  const emitted = [];
  const component = loadSource(
    new URL("../src/components/chat/ChatContextMenu.vue", import.meta.url),
    { "@lucide/vue": {} },
  ).default;
  const menu = mountSetup({
    setup: (_, ctx) =>
      component.setup(
        { modelValue: true, position: [1, 2], items: [] },
        { ...ctx, emit: (...args) => emitted.push(args) },
      ),
  });
  try {
    menu.state.choose("move:p1");
    assert.deepEqual(emitted, [
      ["update:modelValue", false],
      ["select", "move:p1"],
    ]);
  } finally {
    menu.stop();
  }
});

test("the project menu edits, pins and deletes the project it was opened on", async () => {
  const emitted = [];
  let confirmed = false;
  const component = loadSource(
    new URL("../src/components/chat/ProjectList.vue", import.meta.url),
    {
      "@lucide/vue": { Pencil: "Pencil", Pin: "Pin", PinOff: "PinOff", Trash2: "Trash2" },
      "@/i18n/composables": i18n,
      "@/utils/chatPreferences": { chatPreferences: () => ({ global: {} }) },
      "@/utils/confirmDialog": {
        askForConfirmation: async () => confirmed,
        useConfirmDialog: () => null,
      },
      "@/composables/useProjects": { SESSION_DRAG_TYPE: "x" },
      "@/components/chat/ChatContextMenu.vue": {},
      "@/components/chat/SidebarSessionRow.vue": {},
    },
  ).default;
  const list = mountSetup({
    setup: (_, ctx) =>
      component.setup(
        {
          projects: [],
          projectSessions: {},
          loadingProjectIds: [],
          selectedProjectId: null,
          activeSessionId: null,
        },
        { ...ctx, emit: (...args) => emitted.push(args) },
      ),
  });
  try {
    const project = { project_id: "p1", title: "Docs", pinned: true };
    list.state.openProjectMenu({ clientX: 30, clientY: 40 }, project);
    assert.equal(list.state.projectMenuOpen, true);
    assert.deepEqual(plain(list.state.projectMenuPosition), [30, 40]);
    // A pinned project offers to unpin.
    assert.deepEqual(
      plain(
        list.state.projectMenuItems.map((item) => [item.key, item.title, item.icon]),
      ),
      [
        ["edit", "project.edit", "Pencil"],
        ["pin", "actions.unpin", "PinOff"],
        ["delete", "project.delete", "Trash2"],
      ],
    );

    list.state.handleProjectMenu("edit");
    list.state.handleProjectMenu("pin");
    // A declined confirmation deletes nothing.
    list.state.handleProjectMenu("delete");
    await new Promise((resolve) => setTimeout(resolve));
    assert.deepEqual(plain(emitted), [
      ["editProject", project],
      ["pinProject", project],
    ]);
    confirmed = true;
    list.state.handleProjectMenu("delete");
    await new Promise((resolve) => setTimeout(resolve));
    assert.deepEqual(emitted.at(-1), ["deleteProject", "p1"]);
  } finally {
    list.stop();
  }
});

// Run the named top-level functions of Chat.vue's script with `context` as
// their globals (Chat.vue is too large to mount here).
function chatFunctions(names, context) {
  const source = readFileSync(
    new URL("../src/components/chat/Chat.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile("chat.ts", source, ts.ScriptTarget.Latest, true);
  const found = ast.statements.filter(
    (node) => ts.isFunctionDeclaration(node) && names.includes(node.name?.text),
  );
  assert.equal(found.length, names.length);
  vm.runInNewContext(
    ts.transpile(found.map((node) => node.getText(ast)).join("\n"), {
      target: ts.ScriptTarget.ES2022,
    }),
    context,
  );
  return context;
}

function chatContext(overrides = {}) {
  const calls = [];
  const record = (name, result) => async (...args) => {
    calls.push([name, ...args]);
    return result;
  };
  return chatFunctions(
    [
      "sessionProjectId",
      "toggleSessionPin",
      "toggleProjectPin",
      "openSessionMenu",
      "handleSessionMenu",
    ],
    {
      calls,
      projectSessionsById: { value: { p1: [{ session_id: "s2", pinned: true }] } },
      sessionProjects: {},
      menuSession: { value: null },
      sessionMenuOpen: { value: false },
      sessionMenuPosition: { value: [0, 0] },
      chatApi: { updateSession: record("update", { data: { status: "ok" } }) },
      setProjectPinned: record("pinProject", true),
      getSessions: record("getSessions"),
      loadProjectSessions: record("loadProjectSessions"),
      openSessionEditDialog: (id) => calls.push(["edit", id]),
      deleteSidebarSession: record("delete"),
      moveSessionToProject: record("move"),
      toast: { error: (message) => calls.push(["toast.error", message]) },
      tm: (key) => key,
      console: { error() {} },
      ...overrides,
    },
  );
}

test("pinning a conversation saves the new state and reloads the list it is in", async () => {
  const chat = chatContext();
  await chat.toggleSessionPin({ session_id: "s1" });
  assert.deepEqual(plain(chat.calls), [
    ["update", "s1", { pinned: true }],
    ["getSessions"],
  ]);

  // A pinned conversation inside a project is unpinned; only the project reloads.
  chat.calls.length = 0;
  await chat.toggleSessionPin({ session_id: "s2", pinned: true });
  assert.deepEqual(plain(chat.calls), [
    ["update", "s2", { pinned: false }],
    ["loadProjectSessions", "p1"],
  ]);

  const failing = chatContext({
    chatApi: { updateSession: async () => ({ data: { status: "error" } }) },
  });
  await failing.toggleSessionPin({ session_id: "s1" });
  assert.deepEqual(failing.calls, [["toast.error", "conversation.updateFailed"]]);

  const project = chatContext({ setProjectPinned: async () => false });
  await project.toggleProjectPin({ project_id: "p1", pinned: false });
  assert.deepEqual(project.calls, [["toast.error", "conversation.updateFailed"]]);
});

test("the conversation menu acts on the conversation it was opened on", async () => {
  const chat = chatContext();
  const session = { session_id: "s2", display_name: "Two", pinned: true };
  chat.openSessionMenu({ clientX: 5, clientY: 9 }, session);
  assert.equal(chat.sessionMenuOpen.value, true);
  assert.deepEqual(plain(chat.sessionMenuPosition.value), [5, 9]);

  await chat.handleSessionMenu("edit");
  await chat.handleSessionMenu("move:p2");
  // An empty target takes the conversation out of its project.
  await chat.handleSessionMenu("move:");
  await chat.handleSessionMenu("delete");
  assert.deepEqual(plain(chat.calls), [
    ["edit", "s2"],
    ["move", "s2", "p2"],
    ["move", "s2", null],
    ["delete", session],
  ]);

  chat.calls.length = 0;
  await chat.handleSessionMenu("pin");
  assert.deepEqual(plain(chat.calls[0]), ["update", "s2", { pinned: false }]);
});
