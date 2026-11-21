import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { parse } from "vue/compiler-sfc";

const read = (path) =>
  readFileSync(new URL(path, import.meta.url), "utf8").trimStart();

function findElements(node, predicate, found = []) {
  if (predicate(node)) found.push(node);
  for (const child of node.children || []) findElements(child, predicate, found);
  return found;
}

const chat = parse(read("../src/components/chat/Chat.vue")).descriptor;
const workbench = parse(read("../src/components/chat/ChatWorkbench.vue"))
  .descriptor;
const attr = (node, name) =>
  node.props.find(
    (prop) =>
      prop.name === name ||
      (prop.name === "bind" && prop.arg?.content === name) ||
      (prop.name === "on" && prop.arg?.content === name),
  );

test("the workbench button stays in the top bar and toggles the workbench", () => {
  const [teleport] = findElements(
    chat.template.ast,
    (node) =>
      node.tag === "Teleport" &&
      node.props.some((prop) => prop.value?.content === "#chat-workbench-header"),
  );
  const [button] = findElements(teleport, (node) => node.tag === "button");
  // No v-if: the button keeps its place while the workbench is open.
  assert.equal(attr(button, "if"), undefined);
  assert.equal(attr(button, "aria-pressed").exp.content, "workbenchVisible");

  const run = new Function(
    "scope",
    `with (scope) { ${attr(button, "click").exp.content} }`,
  );
  const opened = [];
  const scope = (visible, tabs) => ({
    workbenchVisible: visible,
    workbench: { open: visible, tabs },
    openWorkbenchPage: () => opened.push("launcher"),
  });

  const open = scope(true, [{}]);
  run(open);
  assert.equal(open.workbench.open, false, "second click closes it");

  const hidden = scope(false, [{}]);
  run(hidden);
  assert.equal(hidden.workbench.open, true, "reopens the saved tabs");

  run(scope(false, []));
  assert.deepEqual(opened, ["launcher"], "no tabs yet: opens a new tab");
});

test("the workbench keeps its tabs and buttons inside its card", () => {
  const [element] = findElements(
    chat.template.ast,
    (node) => node.tag === "ChatWorkbench",
  );
  // Without a header target the workbench header is not teleported into the
  // top bar, where it used to replace the other icons.
  assert.equal(attr(element, "header-target"), undefined);
  assert.equal(attr(element, "headerTarget"), undefined);

  const controls = findElements(
    workbench.template.ast,
    (node) => node.props?.some((prop) => prop.value?.content === "workbench-controls"),
  )[0];
  const icons = findElements(controls, (node) => /^[A-Z]/.test(node.tag || ""))
    .map((node) => node.tag);
  assert.deepEqual(icons.slice(-1), ["X"], "closes with an X");
  assert.ok(!icons.includes("PanelRightClose"));
});

test("expanded covers the chat area only and panels open as cards", () => {
  const css = workbench.styles.map((style) => style.content).join("\n");
  const expanded = css.match(
    /@media \(min-width: 960px\) \{[^@]*?\.chat-workbench\.expanded \{([^}]*)\}/,
  );
  assert.ok(expanded, "desktop rule for the expanded workbench");
  assert.match(expanded[1], /position: absolute/);
  assert.doesNotMatch(css, /\.chat-workbench\.expanded \{\s*position: fixed/);
  assert.match(
    chat.styles.map((style) => style.content).join("\n"),
    /\.chat-ui \{[^}]*position: relative/,
  );

  const panels = read("../src/components/chat/chatPanelTransition.css");
  const card = panels.match(/\.chat-ui > aside\.chat-side-panel \{([^}]*)\}/);
  assert.ok(card, "shared card rule for right panels");
  assert.match(card[1], /border-radius/);
  assert.match(card[1], /margin: 0 var\(--chat-panel-gap\)/);
});

test("an open panel's top bar button keeps its highlight", () => {
  const header = parse(
    read("../src/layouts/full/vertical-header/VerticalHeader.vue"),
  ).descriptor.styles.map((style) => style.content).join("\n");
  // The generic header button rule clears backgrounds with !important, so the
  // active rule has to outrank `.top-header .header-actions .v-btn`.
  assert.match(header, /\.top-header \.header-actions \.v-btn \{[^}]*background: transparent !important/);
  assert.match(
    header,
    /\.top-header \.header-actions \.v-btn\.workspace-files-trigger--active \{[^}]*background: rgba\(var\(--v-theme-on-surface\), 0\.08\) !important/,
  );
});

async function loadCatalogModule(fetchWithAuth) {
  const { default: ts } = await import("typescript");
  const vm = await import("node:vm");
  const { ref } = await import("vue");
  const source = read("../src/composables/useWorkbenchViews.ts").replace(
    /^import .*$/gm,
    "",
  );
  const context = vm.createContext({ exports: {}, ref, fetchWithAuth });
  vm.runInContext(
    ts.transpile(source, {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    }),
    context,
  );
  return context.exports.useWorkbenchViews;
}

test("the launcher and the workbench share one view catalog request", async () => {
  let calls = 0;
  let respond;
  const useWorkbenchViews = await loadCatalogModule(() => {
    calls += 1;
    return new Promise((resolve) => (respond = resolve));
  });
  const workbenchSide = useWorkbenchViews();
  const launcherSide = useWorkbenchViews();
  const both = Promise.all([workbenchSide.load(), launcherSide.load()]);
  assert.equal(calls, 1, "a load in flight is shared");
  respond({ ok: true, json: async () => ({ data: [{ name: "usage" }] }) });
  await both;
  assert.equal(launcherSide.views.value.length, 1);
  assert.equal(workbenchSide.failed.value, false);
  assert.doesNotMatch(
    read("../src/components/chat/WorkbenchLauncher.vue"),
    /fetchWithAuth/,
    "the launcher reads the shared catalog",
  );

  const failing = await loadCatalogModule(async () => ({ ok: false }));
  const catalog = failing();
  await catalog.load();
  assert.equal(catalog.failed.value, true);
});

test("the + button shows only when there is a view to add or the list failed", () => {
  const [button] = findElements(
    workbench.template.ast,
    (node) =>
      node.tag === "button" &&
      attr(node, "title")?.exp?.content === "tm('workbench.newTab')",
  );
  const shown = new Function(
    "scope",
    `with (scope) { return Boolean(${attr(button, "if").exp.content}) }`,
  );
  assert.equal(shown({ catalogViews: [], catalogFailed: false }), false);
  assert.equal(shown({ catalogViews: [{}], catalogFailed: false }), true);
  assert.equal(shown({ catalogViews: [], catalogFailed: true }), true, "keeps retry reachable");
});
