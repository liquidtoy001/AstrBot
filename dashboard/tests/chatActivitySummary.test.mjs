import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { reactive } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

const toolKinds = loadSource(new URL("../src/utils/toolKinds.ts", import.meta.url));

// The summary functions, cut out of useMessages.ts like the history tests do.
function activityFunctions() {
  const source = readFileSync(
    new URL("../src/composables/useMessages.ts", import.meta.url),
    "utf8",
  );
  const ast = ts.createSourceFile("messages.ts", source, ts.ScriptTarget.Latest, true);
  const names = new Set(["reasoningActivityCounts", "reasoningActivityTitle"]);
  const functions = [];
  const visit = (node) => {
    if (ts.isFunctionDeclaration(node) && names.has(node.name?.text)) {
      functions.push(node.getText(ast));
      found.add(node.name.text);
    }
    ts.forEachChild(node, visit);
  };
  const found = new Set();
  visit(ast);
  // These tests run the helpers extracted by name; name them if one moved.
  const missing = [...names].filter((name) => !found.has(name));
  assert.deepEqual(missing, [], `useMessages.ts no longer defines: ${missing}`);
  const context = vm.createContext({ exports: {}, TOOL_KINDS: toolKinds.TOOL_KINDS });
  vm.runInContext(ts.transpile(functions.join("\n")), context);
  return context;
}

test("reply summary splits commands, files, sub-agents and other tools", () => {
  const { reasoningActivityCounts, reasoningActivityTitle } = activityFunctions();
  const counts = reasoningActivityCounts([
    { type: "think", think: "plan" },
    { type: "think", think: " " },
    {
      type: "tool_call",
      tool_calls: [
        { name: "astrbot_execute_shell" },
        { name: "astrbot_execute_python" },
        { name: "spawn_agent" },
        { name: "wait_agent" },
        { name: "astrbot_file_write_tool", args: { path: "a" } },
        { name: "astrbot_file_edit_tool", args: { file_path: "a" } },
        { name: "other" },
      ],
    },
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(counts)), {
    thinkCount: 1,
    toolCount: 7,
    commandCount: 2,
    subagentCount: 1,
    subagentControlCalls: 1,
    fileCount: 1,
    fileEditCalls: 2,
  });
  const tm = (key, params) =>
    key === "reasoning.summarySeparator" ? "," : `${key}:${params?.count ?? ""}`;
  assert.equal(
    reasoningActivityTitle(counts, tm),
    "reasoning.thinkSummary:1,reasoning.commandSummary:2,reasoning.fileSummary:1,reasoning.subagentSummary:1,reasoning.otherToolSummary:1",
  );
  // Only unknown tools: the plain "used N tools" wording.
  assert.equal(
    reasoningActivityTitle(
      reasoningActivityCounts([{ type: "tool_call", tool_calls: [{ name: "other" }] }]),
      tm,
    ),
    "reasoning.toolSummary:1",
  );
  assert.equal(reasoningActivityTitle(reasoningActivityCounts([]), tm), "reasoning.thinking:");
});

function toolTitle(toolCall) {
  const component = loadSource(
    new URL("../src/components/chat/message_list_comps/ToolCallCard.vue", import.meta.url),
    {
      // The file change undo button is not used by these cards.
      "@/api/v1": { chatApi: {} },
      "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) },
      "@/utils/toolKinds": toolKinds,
    },
  ).default;
  const mounted = mountSetup(
    { setup: (_, ctx) => component.setup(reactive({ toolCall }), ctx) },
  );
  const summary = mounted.state.toolSummary;
  mounted.stop();
  return summary ? JSON.parse(JSON.stringify(summary)) : summary;
}

test("tool cards name the command or file, or fall back to the tool name", () => {
  assert.deepEqual(
    toolTitle({ name: "astrbot_execute_shell", arguments: '{"command":"\\n pwd\\nls"}' }),
    { verb: "toolSummary.run", target: "pwd" },
  );
  const long = toolTitle({ name: "astrbot_file_write_tool", args: { path: "x".repeat(81) } });
  assert.equal(long.target, "x".repeat(77) + "…");
  assert.deepEqual(toolTitle({ name: "wait_agent" }), { verb: "toolSummary.wait", target: "" });
  for (const call of [
    { name: "unknown" },
    { name: "astrbot_execute_shell", args: "invalid" },
    { name: "astrbot_execute_shell", args: { command: " \n" } },
  ]) {
    assert.equal(toolTitle(call), null);
  }
});
