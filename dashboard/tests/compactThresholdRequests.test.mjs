import assert from "node:assert/strict";
import test from "node:test";
import { messagesHarness } from "./helpers/messagesHarness.mjs";

// The per-conversation compaction threshold travels on every request path,
// next to the other stored options.
for (const transport of ["sse", "websocket", "regenerate"]) {
  test(`${transport} requests carry the stored compaction threshold`, async () => {
    const h = messagesHarness({
      permission_mode: "workspace",
      compact_threshold: 64000,
    });
    try {
      if (transport === "regenerate")
        void h.messages.regenerateMessage("one", h.bot);
      else h.send(transport);
      await new Promise((resolve) => setImmediate(resolve));
      const payload =
        transport === "websocket"
          ? h.sockets[0].sent
          : JSON.parse(h.requests[0].request.body);
      assert.equal(payload.compact_threshold, 64000);
      assert.equal(payload.permission_mode, "workspace");
    } finally {
      h.stop();
    }
  });
}
