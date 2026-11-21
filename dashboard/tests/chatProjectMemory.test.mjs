import assert from "node:assert/strict";
import test from "node:test";
import { nextTick, reactive } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

const plain = (value) => JSON.parse(JSON.stringify(value));

function mountDialog(props) {
  const emitted = [];
  const component = loadSource(
    new URL("../src/components/chat/ProjectDialog.vue", import.meta.url),
    {
      "@/i18n/composables": {
        useI18n: () => ({ t: (key) => key }),
        useModuleI18n: () => ({ tm: (key) => key }),
      },
      "@/utils/desktopRuntime": {
        getDesktopRuntimeInfo: async () => ({ isDesktopRuntime: false }),
      },
      "@/components/shared/EmojiPicker.vue": {},
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

test("the project dialog loads and saves the shared memory switch", async () => {
  const props = reactive({
    modelValue: false,
    project: {
      project_id: "p1",
      title: "Docs",
      workspace_type: "project",
      shared_memory: true,
    },
    errorMessage: "",
    saving: false,
  });
  const dialog = mountDialog(props);
  try {
    props.modelValue = true;
    await nextTick();
    assert.equal(dialog.state.form.shared_memory, true);

    dialog.state.form.shared_memory = false;
    dialog.state.handleSave();
    assert.equal(dialog.emitted.at(-1)[0], "save");
    assert.equal(dialog.emitted.at(-1)[1].shared_memory, false);
    assert.equal(dialog.emitted.at(-1)[2], "p1");

    // A new project starts with shared memory off.
    props.modelValue = false;
    props.project = null;
    await nextTick();
    props.modelValue = true;
    await nextTick();
    assert.equal(dialog.state.form.shared_memory, false);
    dialog.state.form.title = "New";
    dialog.state.form.shared_memory = true;
    dialog.state.handleSave();
    assert.deepEqual(plain(dialog.emitted.at(-1)[1]), {
      emoji: "📁",
      title: "New",
      description: "",
      workspace_type: "project",
      workspace_path: "",
      shared_memory: true,
    });
  } finally {
    dialog.stop();
  }
});

test("saving a project sends the shared memory switch to the server", async () => {
  const calls = [];
  const { useProjects } = loadSource(
    new URL("../src/composables/useProjects.ts", import.meta.url),
    {
      "@/api/v1": {
        chatApi: {
          listProjects: async () => ({ data: { status: "ok", data: [] } }),
          createProject: async (body) => {
            calls.push(["create", body]);
            return { data: { status: "ok", data: {} } };
          },
          updateProject: async (id, body) => {
            calls.push(["update", id, body]);
            return { data: { status: "ok" } };
          },
        },
      },
    },
  );
  const projects = useProjects();
  await projects.createProject("New", "📁", "", "project", "", true);
  await projects.updateProject("p1", "New", "📁", "", "project", "", false);
  assert.equal(calls[0][1].shared_memory, true);
  assert.equal(calls[1][2].shared_memory, false);
});
