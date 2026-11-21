<template>
  <section class="bot-session-view">
    <header class="bot-session-header">
      <h2 class="bot-session-name">{{ session.display_name }}</h2>
      <div class="bot-session-meta" :title="session.umo">
        {{ session.umo }}
      </div>
      <v-alert type="info" variant="tonal" density="compact" class="mt-3">
        {{ tm("botSessions.readOnly") }}
      </v-alert>
      <v-select
        v-if="conversations.length > 1"
        v-model="conversationId"
        :items="conversationItems"
        :label="tm('botSessions.conversation')"
        variant="outlined"
        density="compact"
        hide-details
        class="mt-3"
      />
    </header>

    <div v-if="loading" class="bot-session-state">
      <v-progress-circular indeterminate size="28" width="3" />
    </div>
    <ChatLoadError
      v-else-if="failed"
      class="bot-session-state"
      :message="tm('botSessions.historyFailed')"
      @retry="loadConversations"
    />
    <div v-else-if="!conversations.length" class="bot-session-state">
      {{ tm("botSessions.noConversation") }}
    </div>
    <ConversationHistoryPreview
      v-else
      :key="conversationId"
      class="bot-session-history"
      :messages="messages"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { conversationApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import ChatLoadError from "@/components/chat/ChatLoadError.vue";
import ConversationHistoryPreview from "@/components/conversation/ConversationHistoryPreview.vue";
import type { BotSession } from "@/components/chat/BotSessionList.vue";

// Read-only view of a bot session on another platform. It shows the model
// context of one of the session's conversations; nothing can be sent from here.
const props = defineProps<{ session: BotSession }>();

const { tm } = useModuleI18n("features/chat");
const conversations = ref<{ cid: string; title?: string; updated_at?: number }[]>(
  [],
);
const conversationId = ref("");
const messages = ref<unknown[]>([]);
const loading = ref(false);
const failed = ref(false);
// Drops the result of a request the user has already moved on from.
let requestId = 0;

const conversationItems = computed(() =>
  conversations.value.map((conversation) => ({
    title: [
      conversation.title || conversation.cid.slice(0, 8),
      conversation.updated_at
        ? new Date(conversation.updated_at * 1000).toLocaleString()
        : "",
    ]
      .filter(Boolean)
      .join(" · "),
    value: conversation.cid,
  })),
);

async function loadConversations() {
  const current = ++requestId;
  loading.value = true;
  failed.value = false;
  conversations.value = [];
  conversationId.value = "";
  messages.value = [];
  try {
    const response = await conversationApi.list({
      umo: props.session.umo,
      sort_by: "updated_at",
      sort_order: "desc",
      page_size: 100,
      include_history: false,
    });
    if (current !== requestId) return;
    if (response.data.status !== "ok") throw new Error(response.data.message || "");
    // The server matches the UMO as a substring; keep the exact session only.
    conversations.value = (response.data.data?.conversations || []).filter(
      (conversation: { user_id?: string }) =>
        conversation.user_id === props.session.umo,
    );
    // The most recently active conversation is shown first.
    conversationId.value = conversations.value[0]?.cid || "";
    if (!conversationId.value) loading.value = false;
  } catch (error) {
    if (current !== requestId) return;
    console.error("Failed to load the bot session:", error);
    failed.value = true;
    loading.value = false;
  }
}

async function loadMessages(cid: string) {
  if (!cid) return;
  const current = ++requestId;
  loading.value = true;
  failed.value = false;
  try {
    const response = await conversationApi.get(props.session.umo, cid);
    if (current !== requestId) return;
    if (response.data.status !== "ok") throw new Error(response.data.message || "");
    const history = response.data.data?.history || [];
    const parsed = typeof history === "string" ? JSON.parse(history) : history;
    messages.value = Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    if (current !== requestId) return;
    console.error("Failed to load the bot session history:", error);
    failed.value = true;
  } finally {
    if (current === requestId) loading.value = false;
  }
}

watch(() => props.session.umo, loadConversations, { immediate: true });
watch(conversationId, loadMessages);
</script>

<style scoped>
.bot-session-view {
  flex: 1;
  min-height: 0;
  width: 100%;
  max-width: 920px;
  margin: 0 auto;
  padding: 16px 24px 0;
  display: flex;
  flex-direction: column;
}

.bot-session-header {
  flex: 0 0 auto;
  padding-bottom: 12px;
}

.bot-session-name {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.3;
}

.bot-session-meta {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 12px;
}

.bot-session-state {
  padding: 32px 0;
  display: flex;
  justify-content: center;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 14px;
}

.bot-session-history {
  flex: 1;
  min-height: 0;
}
</style>
