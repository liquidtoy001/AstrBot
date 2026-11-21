<template>
  <div class="bot-session-list">
    <v-progress-linear
      v-if="loading"
      color="primary"
      height="2"
      indeterminate
      :aria-label="tm('botSessions.loading')"
    />
    <ChatLoadError
      v-else-if="failed"
      :message="tm('botSessions.loadFailed')"
      @retry="load"
    />
    <div v-else-if="!groups.length" class="bot-session-empty">
      {{ tm("botSessions.empty") }}
    </div>
    <section v-for="group in groups" :key="group.key" class="bot-session-group">
      <div class="bot-session-group-header">
        {{ tm(`botSessions.${group.key}`) }}
        <span class="bot-session-count">{{ group.sessions.length }}</span>
      </div>
      <div
        v-for="session in group.sessions"
        :key="session.umo"
        class="bot-session-row"
        :class="{ active: activeUmo === session.umo }"
        role="button"
        tabindex="0"
        :title="session.umo"
        @click="emit('select', session)"
        @keydown.enter="emit('select', session)"
        @keydown.space.prevent="emit('select', session)"
      >
        <span class="bot-session-title">{{ session.display_name }}</span>
        <span class="bot-session-platform">{{ session.platform }}</span>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { sessionApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import ChatLoadError from "@/components/chat/ChatLoadError.vue";

/** A session of the bot on a messaging platform, identified by its UMO. */
export interface BotSession {
  umo: string;
  platform: string;
  message_type: string;
  display_name: string;
}

// The bot's private and group chats on other platforms, newest activity
// first. ChatUI's own conversations are listed elsewhere in the sidebar.
defineProps<{ activeUmo?: string | null }>();
const emit = defineEmits<{ select: [session: BotSession] }>();

const { tm } = useModuleI18n("features/chat");
const sessions = ref<BotSession[]>([]);
const loading = ref(false);
const failed = ref(false);

const groups = computed(() =>
  (["private", "group", "other"] as const)
    .map((key) => ({
      key,
      sessions: sessions.value.filter((session) => {
        const type = session.message_type.toLowerCase();
        const kind = type.includes("group")
          ? "group"
          : type.includes("friend") || type.includes("private")
            ? "private"
            : "other";
        return kind === key;
      }),
    }))
    .filter((group) => group.sessions.length),
);

async function load() {
  loading.value = true;
  failed.value = false;
  try {
    const response = await sessionApi.activeUmos();
    if (response.data.status !== "ok") throw new Error(response.data.message || "");
    const infos: BotSession[] = response.data.data?.umo_infos || [];
    sessions.value = infos.filter((info) => info.platform !== "webchat");
  } catch (error) {
    console.error("Failed to load bot sessions:", error);
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.bot-session-list {
  flex: 1;
  overflow-y: auto;
  padding: 2px 16px 12px;
}

.bot-session-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.bot-session-group-header {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 13px;
  font-weight: 700;
}

.bot-session-count {
  color: var(--chat-muted);
  font-weight: 400;
}

.bot-session-row {
  min-height: 30px;
  border-radius: var(--astrbot-radius-navigation);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  cursor: pointer;
}

.bot-session-row:hover {
  background: var(--chat-session-active-bg);
}

.bot-session-row.active {
  background: var(--chat-session-selected-bg);
}

.bot-session-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.bot-session-platform {
  flex: 0 1 auto;
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--chat-muted);
  font-size: 12px;
}

.bot-session-empty {
  padding: 10px;
  color: var(--chat-muted);
  font-size: 13px;
}
</style>
