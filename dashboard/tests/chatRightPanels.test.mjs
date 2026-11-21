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
