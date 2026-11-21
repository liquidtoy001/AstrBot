import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { nextTick, reactive } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

const DRAG_TYPE = "application/x-astrbot-session";
const plain = (value) => JSON.parse(JSON.stringify(value));
const i18n = {
  useI18n: () => ({ t: (key) => key }),
  useModuleI18n: () => ({ tm: (key) => key }),
};

function mountDialog(props) {
  const emitted = [];
  const component = loadSource(
    new URL("../src/components/chat/SessionEditDialog.vue", import.meta.url),
    {
      "@lucide/vue": {},
      "@/i18n/composables": i18n,
      "@/utils/desktopRuntime": {
        getDesktopRuntimeInfo: async () => ({ isDesktopRuntime: false }),
      },
    },
  ).default;
  const mounted = mountSetup({
    setup: (_, ctx) =>
      component.setup(props, {
        ...ctx,
        emit: (...args) => emitted.push(args),
      }),
  });
  return { ...mounted, emitted };
}

test("the edit dialog starts from the conversation and saves trimmed fields", async () => {
  const props = reactive({
    modelValue: false,
    session: { display_name: "Notes", project_id: "p1", workspace_path: "D:/work" },
    projects: [{ project_id: "p1", title: "Docs", emoji: "📚" }],
    saving: false,
    errorMessage: "",
  });
  const dialog = mountDialog(props);
  try {
    assert.deepEqual(plain(dialog.state.projectItems), [
      { title: "conversation.noProject", value: "" },
      { title: "📚 Docs", value: "p1" },
    ]);
    props.modelValue = true;
    await nextTick();
    assert.deepEqual(plain(dialog.state.form), props.session);

    dialog.state.form.display_name = "  Renamed ";
    dialog.state.form.project_id = "";
    // Vuetify sets a cleared field to null.
    dialog.state.form.workspace_path = null;
    dialog.state.save();
    assert.deepEqual(plain(dialog.emitted), [
      ["save", { display_name: "Renamed", project_id: "", workspace_path: "" }],
    ]);
  } finally {
    dialog.stop();
  }
});

test("a project accepts a dragged conversation and ignores other drags", () => {
  const emitted = [];
  const component = loadSource(
    new URL("../src/components/chat/ProjectList.vue", import.meta.url),
    {
      "@lucide/vue": {},
      "@/i18n/composables": i18n,
      "@/utils/chatPreferences": { chatPreferences: () => ({ global: {} }) },
      "@/utils/confirmDialog": {
        askForConfirmation: async () => true,
        useConfirmDialog: () => null,
      },
      "@/composables/useProjects": { SESSION_DRAG_TYPE: DRAG_TYPE },
      "@/components/chat/ChatContextMenu.vue": {},
      "@/components/chat/SidebarSessionRow.vue": {},
    },
  ).default;
  const props = {
    projects: [],
    projectSessions: {},
    loadingProjectIds: [],
    selectedProjectId: null,
    activeSessionId: null,
  };
  const list = mountSetup({
    setup: (_, ctx) =>
      component.setup(props, { ...ctx, emit: (...args) => emitted.push(args) }),
  });
  const dragEvent = (types, data = "") => ({
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
    dataTransfer: { types, getData: (type) => (type === DRAG_TYPE ? data : "") },
  });
  try {
    // A file dragged over the sidebar is not a conversation.
    const files = dragEvent(["Files"]);
    list.state.handleSessionDragOver(files, "p1");
    assert.equal(files.prevented, false);
    assert.equal(list.state.dropProjectId, null);

    const over = dragEvent([DRAG_TYPE]);
    list.state.handleSessionDragOver(over, "p1");
    assert.equal(over.prevented, true);
    assert.equal(list.state.dropProjectId, "p1");

    list.state.handleSessionDrop(dragEvent([DRAG_TYPE], "s1"), "p1");
    assert.equal(list.state.dropProjectId, null);
    list.state.handleSessionDrop(dragEvent(["Files"]), "p1");
    assert.deepEqual(emitted, [["moveSession", "s1", "p1"]]);
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
  const context = {
    calls,
    sessions: { value: [{ session_id: "s1", display_name: "One" }] },
    projects: {
      value: [
        { project_id: "p1", title: "Docs", emoji: "📚" },
        { project_id: "p2", title: "Code" },
      ],
    },
    projectSessions: { value: [] },
    projectSessionsById: {
      value: { p1: [{ session_id: "s2", display_name: "Two", workspace_path: "shared" }] },
    },
    sessionProjects: {},
    sessionDetails: {},
    editingSessionId: { value: "" },
    editingSession: { value: null },
    sessionEditOpen: { value: false },
    sessionEditError: { value: "" },
    savingSession: { value: false },
    addSessionToProject: record("add", true),
    removeSessionFromProject: record("remove", true),
    getSessions: record("getSessions"),
    loadProjectSessions: record("loadProjectSessions"),
    chatApi: { updateSession: record("update", { data: { status: "ok" } }) },
    toast: {
      error: (message) => calls.push(["toast.error", message]),
      success: (message) => calls.push(["toast.success", message]),
    },
    tm: (key) => key,
    console,
    ...overrides,
  };
  return chatFunctions(
    ["openSessionEditDialog", "saveSessionEdit", "sessionProjectId", "moveSessionToProject"],
    context,
  );
}

test("moving a conversation updates its project and refreshes both lists", async () => {
  const chat = chatContext();
  assert.equal(await chat.moveSessionToProject("s1", "p1"), true);
  assert.deepEqual(plain(chat.sessionProjects.s1), {
    project_id: "p1",
    title: "Docs",
    emoji: "📚",
  });
  assert.deepEqual(chat.calls, [
    ["add", "s1", "p1"],
    ["getSessions"],
    ["loadProjectSessions", "p1"],
    ["toast.success", "conversation.movedToProject"],
  ]);

  // From one project to another: both project lists are reloaded.
  chat.calls.length = 0;
  await chat.moveSessionToProject("s2", "p2");
  assert.deepEqual(chat.calls.slice(0, 4), [
    ["add", "s2", "p2"],
    ["getSessions"],
    ["loadProjectSessions", "p1"],
    ["loadProjectSessions", "p2"],
  ]);

  // Out of the project.
  chat.calls.length = 0;
  await chat.moveSessionToProject("s2", null);
  assert.equal(chat.sessionProjects.s2, null);
  assert.deepEqual(chat.calls[0], ["remove", "s2"]);
});

test("a move to the same place does nothing and a failed move is reported", async () => {
  const chat = chatContext();
  assert.equal(await chat.moveSessionToProject("s2", "p1"), true);
  assert.equal(await chat.moveSessionToProject("s1", null), true);
  assert.equal(await chat.moveSessionToProject("", "p1"), true);
  assert.deepEqual(chat.calls, []);

  const failing = chatContext({ addSessionToProject: async () => false });
  assert.equal(await failing.moveSessionToProject("s1", "p1"), false);
  assert.deepEqual(failing.calls, [["toast.error", "conversation.moveFailed"]]);
  assert.equal(failing.sessionProjects.s1, undefined);
});

test("saving the dialog sends the path only when it changed and moves the conversation", async () => {
  const chat = chatContext();
  chat.openSessionEditDialog("s2");
  assert.deepEqual(plain(chat.editingSession.value), {
    display_name: "Two",
    project_id: "p1",
    workspace_path: "shared",
  });

  // Renaming must not revalidate an unchanged path.
  await chat.saveSessionEdit({
    display_name: "Renamed",
    project_id: "p1",
    workspace_path: "shared",
  });
  assert.deepEqual(plain(chat.calls), [
    ["update", "s2", { display_name: "Renamed" }],
    ["loadProjectSessions", "p1"],
  ]);
  assert.equal(chat.projectSessionsById.value.p1[0].display_name, "Renamed");
  assert.equal(chat.sessionEditOpen.value, false);

  chat.calls.length = 0;
  chat.openSessionEditDialog("s2");
  await chat.saveSessionEdit({
    display_name: "Renamed",
    project_id: "",
    workspace_path: "",
  });
  assert.deepEqual(plain(chat.calls.slice(0, 2)), [
    ["update", "s2", { display_name: "Renamed", workspace_path: "" }],
    ["remove", "s2"],
  ]);
  assert.equal(chat.projectSessionsById.value.p1[0].workspace_path, null);
});

test("a rejected workspace path keeps the dialog open with the server message", async () => {
  const chat = chatContext({
    chatApi: {
      updateSession: async () => ({
        data: { status: "error", message: "Custom workspace path does not exist" },
      }),
    },
  });
  chat.openSessionEditDialog("s1");
  await chat.saveSessionEdit({
    display_name: "One",
    project_id: "p1",
    workspace_path: "missing",
  });
  assert.equal(chat.sessionEditOpen.value, true);
  assert.equal(chat.sessionEditError.value, "Custom workspace path does not exist");
  assert.equal(chat.savingSession.value, false);
  // Nothing else is applied when the save was refused.
  assert.deepEqual(chat.calls, []);
  assert.equal(chat.sessions.value[0].workspace_path, undefined);
});
