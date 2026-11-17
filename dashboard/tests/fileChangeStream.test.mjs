import assert from "node:assert/strict";
import test from "node:test";
import { ref } from "vue";
import { loadSource } from "./helpers/vueHarness.mjs";

const messages = loadSource(new URL("../src/composables/useMessages.ts", import.meta.url), {
  "@/i18n/composables": { useI18n: () => ({ locale: ref("en-US"), t: (key) => key }) },
  "@/api/v1": { chatApi: {}, fileApi: {} },
  "@/api/http": { fetchWithAuth: async () => ({}) },
  "@/utils/chatViews": { streamViewAction: async () => {}, viewActionKey: () => "" },
  "@/composables/useActionRowChoices": {},
});

test("a streamed tool result keeps its file change preview", () => {
  const change = { change_id: "c1", path: "a.txt", added_count: 1 };
  const record = { content: { type: "bot", message: [] } };
  messages.upsertToolCall(record, { id: "t1", name: "astrbot_file_write_tool", ts: 1 });
  messages.finishToolCall(record, { id: "t1", result: "ok", ts: 2, file_change: change });
  assert.deepEqual(record.content.message[0].tool_calls[0].file_change, change);

  // A result whose call was never seen still keeps the preview.
  messages.finishToolCall(record, { id: "t2", result: "ok", ts: 3, file_change: change });
  assert.deepEqual(record.content.message[1].tool_calls[0].file_change, change);
});
