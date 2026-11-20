import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { loadSource } from "./helpers/vueHarness.mjs";

const { subagentFollowUpRoots } = loadSource(
  new URL("../src/composables/useSessionSubagents.ts", import.meta.url),
  { "@/utils/toolKinds": { TOOL_KINDS: {} }, "@/api/v1": { chatApi: {} } },
);

// The same history normalization that a reload and the idle live refresh use.
function historyNormalizer() {
  const source = readFileSync(
    new URL("../src/composables/useMessages.ts", import.meta.url),
    "utf8",
  );
  const ast = ts.createSourceFile("m.ts", source, ts.ScriptTarget.Latest, true);
  const names = new Set([
    "normalizeHistoryRecord",
    "normalizeMessageParts",
    "normalizePartsInternal",
    "extractReasoningText",
    "isEmptyPlainPart",
    "isThinkingPart",
  ]);
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
  // The test runs the helpers extracted by name; name them if one moved.
  const missing = [...names].filter((name) => !found.has(name));
  assert.deepEqual(missing, [], `useMessages.ts no longer defines: ${missing}`);
  const context = vm.createContext({ exports: {} });
  vm.runInContext(ts.transpile(functions.join("\n")), context);
  return context.normalizeHistoryRecord;
}

const user = (text) => ({
  content: { type: "user", message: [{ type: "plain", text }] },
});
const spawner = (...ids) => ({
  content: {
    type: "bot",
    message: [
      {
        type: "tool_call",
        tool_calls: ids.map((id) => ({
          name: "spawn_agent",
          // History stores the result as JSON text, a live record as an object.
          result: id.startsWith("live")
            ? { agent_id: id }
            : JSON.stringify({ agent_id: id }),
        })),
      },
      { type: "plain", text: "Started" },
    ],
  },
});
const reply = (text, subagentResults) => ({
  content: { type: "bot", message: [{ type: "plain", text }], subagentResults },
});
const roots = (records) => Object.fromEntries(subagentFollowUpRoots(records));

test("a reload groups a stored sub-agent follow-up under the reply that spawned it", () => {
  const normalize = historyNormalizer();
  const records = [
    {
      id: 1,
      content: {
        type: "user",
        message: [{ type: "plain", text: "Spawn three" }],
      },
    },
    {
      id: 2,
      content: {
        type: "bot",
        message: [
          {
            type: "tool_call",
            tool_calls: [
              { name: "spawn_agent", result: '{"agent_id":"aa11"}' },
            ],
          },
        ],
      },
    },
    {
      id: 3,
      content: {
        type: "bot",
        message: [{ type: "plain", text: "All done" }],
        subagent_results: ["aa11"],
      },
    },
  ].map(normalize);
  assert.deepEqual([...records[2].content.subagentResults], ["aa11"]);
  assert.deepEqual(roots(records), { 2: 1 });
});

test("every follow-up of one spawn joins the same bubble, live or stored", () => {
  assert.deepEqual(
    roots([
      user("go"),
      spawner("live1", "aa22"),
      reply("first result", ["aa22"]),
      reply("second result", ["live1"]),
    ]),
    { 2: 1, 3: 1 },
  );
});

test("a user message, an unrelated reply or other agents end the group", () => {
  assert.deepEqual(
    roots([
      spawner("aa11"),
      user("next question"),
      reply("late result", ["aa11"]),
    ]),
    {},
  );
  // A scheduled reminder in between is its own bubble and ends the group.
  assert.deepEqual(
    roots([spawner("aa11"), reply("reminder"), reply("late result", ["aa11"])]),
    {},
  );
  assert.deepEqual(
    roots([spawner("aa11"), reply("other agents", ["bb22"])]),
    {},
  );
  // A follow-up that spawns more agents keeps collecting their results.
  assert.deepEqual(
    roots([
      spawner("aa11"),
      { content: { ...spawner("cc33").content, subagentResults: ["aa11"] } },
      reply("nested result", ["cc33"]),
    ]),
    { 1: 0, 2: 0 },
  );
});
