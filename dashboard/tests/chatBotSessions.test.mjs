import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { reactive } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

const plain = (value) => JSON.parse(JSON.stringify(value));
const settle = () => new Promise((resolve) => setTimeout(resolve));
const i18n = { useModuleI18n: () => ({ tm: (key) => key }) };
const silent = { ...console, error() {} };

function mountList(activeUmos) {
  const component = loadSource(
    new URL("../src/components/chat/BotSessionList.vue", import.meta.url),
    {
      "@/api/v1": { sessionApi: { activeUmos } },
      "@/i18n/composables": i18n,
      "@/components/chat/ChatLoadError.vue": {},
    },
    { console: silent },
  ).default;
  return mountSetup({ setup: (_, ctx) => component.setup({}, ctx) });
}

test("the bot session list groups other platforms' sessions and leaves ChatUI's out", async () => {
  const info = (umo, display_name) => {
    const [platform, message_type] = umo.split(":");
    return { umo, platform, message_type, display_name };
  };
  const list = mountList(async () => ({
    data: {
      status: "ok",
      data: {
        // Newest activity first, as the server returns them.
        umo_infos: [
          info("qq:GroupMessage:100", "Dev group"),
          info("webchat:FriendMessage:webchat!alice!s1", "A ChatUI conversation"),
          info("telegram:FriendMessage:7", "Bob"),
          info("qq:FriendMessage:42", "Carol"),
          info("slack:OtherMessage:c1", "Channel"),
        ],
      },
    },
  }));
  try {
    await settle();
    assert.equal(list.state.failed, false);
    assert.deepEqual(
      plain(list.state.groups).map((group) => [
        group.key,
        group.sessions.map((session) => session.display_name),
      ]),
      [
        ["private", ["Bob", "Carol"]],
        ["group", ["Dev group"]],
        ["other", ["Channel"]],
      ],
    );
  } finally {
    list.stop();
  }

  const failing = mountList(async () => ({ data: { status: "error" } }));
  try {
    await settle();
    assert.equal(failing.state.failed, true);
    assert.equal(failing.state.loading, false);
    assert.deepEqual(plain(failing.state.groups), []);
  } finally {
    failing.stop();
  }
});

test("the bot session view shows the latest conversation of exactly that session", async () => {
  const calls = [];
  const conversations = [
    // The server matches the UMO as a substring, so a longer ID comes back too.
    { user_id: "qq:GroupMessage:1000", cid: "other", updated_at: 30 },
    { user_id: "qq:GroupMessage:100", cid: "new", title: "Latest", updated_at: 20 },
    { user_id: "qq:GroupMessage:100", cid: "old", updated_at: 10 },
  ];
  const histories = {
    new: JSON.stringify([{ role: "user", content: "hi" }]),
    old: [{ role: "assistant", content: "earlier" }],
  };
  const component = loadSource(
    new URL("../src/components/chat/BotSessionView.vue", import.meta.url),
    {
      "@/api/v1": {
        conversationApi: {
          list: async (query) => {
            calls.push(["list", query]);
            return { data: { status: "ok", data: { conversations } } };
          },
          get: async (umo, cid) => {
            calls.push(["get", umo, cid]);
            return { data: { status: "ok", data: { history: histories[cid] } } };
          },
        },
      },
      "@/i18n/composables": i18n,
      "@/components/chat/ChatLoadError.vue": {},
      "@/components/conversation/ConversationHistoryPreview.vue": {},
    },
    { console: silent },
  ).default;
  const props = reactive({
    session: {
      umo: "qq:GroupMessage:100",
      platform: "qq",
      message_type: "GroupMessage",
      display_name: "Dev group",
    },
  });
  const view = mountSetup({ setup: (_, ctx) => component.setup(props, ctx) });
  try {
    await settle();
    assert.deepEqual(plain(calls), [
      [
        "list",
        {
          umo: "qq:GroupMessage:100",
          sort_by: "updated_at",
          sort_order: "desc",
          page_size: 100,
          include_history: false,
        },
      ],
      ["get", "qq:GroupMessage:100", "new"],
    ]);
    assert.deepEqual(
      view.state.conversations.map((conversation) => conversation.cid),
      ["new", "old"],
    );
    assert.deepEqual(plain(view.state.messages), [{ role: "user", content: "hi" }]);
    assert.equal(view.state.loading, false);

    // Choosing another conversation of the session loads its history.
    view.state.conversationId = "old";
    await settle();
    assert.deepEqual(plain(view.state.messages), [
      { role: "assistant", content: "earlier" },
    ]);

    // A session without any conversation shows nothing and stops loading.
    conversations.length = 0;
    props.session = { ...props.session, umo: "qq:FriendMessage:42" };
    await settle();
    assert.deepEqual(plain(view.state.messages), []);
    assert.equal(view.state.conversationId, "");
    assert.equal(view.state.loading, false);
    assert.equal(view.state.failed, false);
  } finally {
    view.stop();
  }
});

test("opening a bot session leaves the current conversation and project", async () => {
  const source = readFileSync(
    new URL("../src/components/chat/Chat.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile("chat.ts", source, ts.ScriptTarget.Latest, true);
  const fn = ast.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name?.text === "selectBotSession",
  );
  const order = [];
  const chat = {
    selectedProjectId: { value: "p1" },
    currSessionId: { value: "s1" },
    replyTarget: { value: {} },
    selectedBotSession: { value: null },
    showChatWorkspace: () => order.push("workspace"),
    basePath: () => "/chat",
    router: {
      push: async (path) => {
        // The session is shown only after the route left the old conversation.
        order.push(["push", path, chat.selectedBotSession.value]);
      },
    },
  };
  vm.runInNewContext(
    ts.transpile(fn.getText(ast), { target: ts.ScriptTarget.ES2022 }),
    chat,
  );
  const session = { umo: "qq:GroupMessage:100" };
  await chat.selectBotSession(session);
  assert.deepEqual(order, ["workspace", ["push", "/chat", null]]);
  assert.equal(chat.selectedProjectId.value, null);
  assert.equal(chat.currSessionId.value, "");
  assert.equal(chat.replyTarget.value, null);
  assert.equal(chat.selectedBotSession.value, session);
});

test("the sidebar rows choose the list and leave the model settings", () => {
  const source = readFileSync(
    new URL("../src/components/chat/Chat.vue", import.meta.url),
    "utf8",
  );
  const script = source.split('<script setup lang="ts">')[1].split("</script>")[0];
  const ast = ts.createSourceFile("chat.ts", script, ts.ScriptTarget.Latest, true);
  const fn = ast.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name?.text === "selectSidebarTab",
  );
  const chat = {
    sidebarTab: { value: "chats" },
    isSidebarCollapsed: { value: false },
    customizer: {
      SET_CHAT_SIDEBAR_COLLAPSED(value) {
        chat.collapsed = value;
      },
    },
    shown: 0,
    showChatWorkspace() {
      this.shown += 1;
    },
  };
  chat.showChatWorkspace = chat.showChatWorkspace.bind(chat);
  vm.runInNewContext(
    ts.transpile(fn.getText(ast), { target: ts.ScriptTarget.ES2022 }),
    chat,
  );
  chat.selectSidebarTab("bots");
  assert.equal(chat.sidebarTab.value, "bots");
  assert.equal(chat.shown, 1);
  assert.equal(chat.collapsed, undefined);

  // From the collapsed rail the sidebar opens to show the chosen list.
  chat.isSidebarCollapsed.value = true;
  chat.selectSidebarTab("chats");
  assert.equal(chat.sidebarTab.value, "chats");
  assert.equal(chat.collapsed, false);

  // The rows sit between the model settings and new chat, bots first.
  const template = source.split("<template>")[1];
  const order = ["actions.providerConfig", "v-for=\"tab in sidebarTabs\"", "actions.newChat"]
    .map((marker) => template.indexOf(marker));
  assert.ok(order.every((index, i) => index > 0 && (i === 0 || index > order[i - 1])));
  assert.match(script, /\{ key: "bots", icon: Bot \},\s*\{ key: "chats", icon: MessagesSquare \}/);
});
