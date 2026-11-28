<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ChevronDown } from "@lucide/vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import { useModuleI18n } from "@/i18n/composables";
import ProviderModelMenu from "@/components/chat/ProviderModelMenu.vue";
import { useChatHeaderStore } from "@/stores/chatHeader";

const route = useRoute();
const router = useRouter();
const { tm } = useModuleI18n("features/provider");
const { tm: tmChat } = useModuleI18n("features/chat");
const isProviderWorkspace = computed(() => route.params.conversationId === "models");
const providerTypes = computed(() => [
  { value: "chat_completion", label: tm("providers.tabs.chatCompletion") },
  { value: "speech_to_text", label: tm("providers.tabs.speechToText") },
  { value: "text_to_speech", label: tm("providers.tabs.textToSpeech") },
]);
const selectedType = computed(() =>
  providerTypes.value.find((type) => type.value === route.query.type) || providerTypes.value[0],
);
const chatHeader = useChatHeaderStore();
const title = computed(() => {
  const t = chatHeader.title.trim();
  const s = chatHeader.subtitle.trim();
  if (t && s) return `${s} / ${t}`;
  return t || s;
});

// In-place rename of the open conversation. The conversation is fixed when
// editing starts, and switching conversations cancels the edit.
const renamable = computed(() => Boolean(chatHeader.titleSessionId));
const renameHint = computed(() => tmChat("conversation.renameTitleHint"));
const editing = ref(false);
const draft = ref("");
const titleEl = ref<HTMLElement | null>(null);
const titleInput = ref<HTMLInputElement | null>(null);
let editingSessionId = "";

async function startRename() {
  if (!renamable.value || editing.value) return;
  editingSessionId = chatHeader.titleSessionId;
  draft.value = chatHeader.title;
  editing.value = true;
  await nextTick();
  titleInput.value?.focus();
  titleInput.value?.select();
}

function finishRename(save: boolean) {
  if (!editing.value) return;
  editing.value = false;
  const name = draft.value.trim();
  if (save && name && name !== chatHeader.title.trim()) {
    chatHeader.REQUEST_RENAME(editingSessionId, name);
  }
}

function onTitleInputKeydown(event: KeyboardEvent) {
  // Enter also confirms IME candidates; leave those to the input method.
  if (event.isComposing) return;
  if (event.key !== "Enter" && event.key !== "Escape") return;
  event.preventDefault();
  finishRename(event.key === "Enter");
  // Keyboard users stay on the title.
  nextTick(() => titleEl.value?.focus());
}

watch(
  () => chatHeader.titleSessionId,
  () => finishRename(false),
);

// Desktop app: the renamable title still drags the window like the rest of the
// header, but only once the mouse moves, so a double-click reaches the rename
// instead of the shell's maximize. Browsers have no Tauri API and skip this.
let dragStart: { x: number; y: number } | null = null;

function onTitleMousedown(event: MouseEvent) {
  dragStart =
    renamable.value && event.button === 0 && event.detail === 1
      ? { x: event.clientX, y: event.clientY }
      : null;
}

function onTitleMousemove(event: MouseEvent) {
  if (!dragStart) return;
  if (!(event.buttons & 1)) {
    dragStart = null;
    return;
  }
  if (Math.abs(event.clientX - dragStart.x) + Math.abs(event.clientY - dragStart.y) < 4) return;
  dragStart = null;
  const tauri = (window as { __TAURI_INTERNALS__?: { invoke: (cmd: string) => Promise<unknown> } })
    .__TAURI_INTERNALS__;
  tauri?.invoke("plugin:window|start_dragging").catch(() => {});
}
</script>

<template>
  <div class="chat-toolbar-context">
    <StyledMenu v-if="isProviderWorkspace" location="bottom start" :offset="8">
      <template #activator="{ props }">
        <button v-bind="props" type="button" class="provider-type-trigger">
          {{ selectedType.label }}
          <ChevronDown :size="16" :stroke-width="1.75" />
        </button>
      </template>
      <v-list-item
        v-for="type in providerTypes"
        :key="type.value"
        class="styled-menu-item"
        :active="selectedType.value === type.value"
        @click="router.push({ path: route.path, query: { ...route.query, type: type.value } })"
      >
        <v-list-item-title>{{ type.label }}</v-list-item-title>
      </v-list-item>
    </StyledMenu>
    <ProviderModelMenu v-else variant="header" />
    <input
      v-if="editing"
      ref="titleInput"
      v-model="draft"
      class="chat-toolbar-context-title chat-toolbar-title-input"
      :aria-label="tmChat('conversation.displayName')"
      @keydown="onTitleInputKeydown"
      @blur="finishRename(true)"
    />
    <span
      v-else-if="title"
      ref="titleEl"
      class="chat-toolbar-context-title"
      :class="{ renamable }"
      :title="renamable ? `${title}\n${renameHint}` : title"
      :tabindex="renamable ? 0 : undefined"
      :role="renamable ? 'button' : undefined"
      :aria-label="renamable ? `${title}, ${renameHint}` : undefined"
      :data-tauri-drag-region="renamable ? undefined : ''"
      @mousedown="onTitleMousedown"
      @mousemove="onTitleMousemove"
      @dblclick="startRename"
      @keydown.enter.prevent="startRename"
      @keydown.f2.prevent="startRename"
      >{{ title }}</span
    >
  </div>
</template>

<style scoped>
.provider-type-trigger {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 20px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.8125rem;
  font-weight: 600;
  white-space: nowrap;
}

.chat-toolbar-context {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

/* Keep the selector compact enough to stack with the title on narrow screens. */
.chat-toolbar-context :deep(.provider-select-menu) {
  height: 20px;
  display: flex;
}

.chat-toolbar-context :deep(.provider-trigger--header) {
  height: 20px;
}

.chat-toolbar-context :deep(.provider-trigger--header .provider-trigger-title) {
  font-size: 0.8125rem;
  line-height: 20px;
}

.chat-toolbar-context
  :deep(.provider-trigger--header .provider-trigger-chevron) {
  font-size: 16px;
}

.chat-toolbar-context-title {
  max-width: 32vw;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.6875rem;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* The title drags the window from script (see onTitleMousemove); the input
   never does, so selecting text cannot move the window. */
.chat-toolbar-context-title.renamable {
  cursor: default;
}

.chat-toolbar-title-input {
  -webkit-app-region: no-drag;
}

.chat-toolbar-context-title.renamable:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.6);
  outline-offset: 2px;
  border-radius: 4px;
}

.chat-toolbar-title-input {
  min-width: 120px;
  padding: 1px 6px;
  border: 1px solid rgba(var(--v-theme-primary), 0.6);
  border-radius: 6px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font-family: inherit;
  outline: none;
}

@media (min-width: 960px) {
  .chat-toolbar-context {
    max-width: min(
      300px,
      calc((100vw - var(--astrbot-chat-sidebar-width, 0px)) * 0.3 - 32px)
    );
    flex-direction: row;
    align-items: center;
  }

  /* Center over the chat pane, independently of the model and action widths. */
  .chat-toolbar-context-title {
    position: absolute;
    top: 50%;
    left: calc(50% + (var(--astrbot-chat-sidebar-width, 0px) - var(--astrbot-active-workbench-width, 0px)) / 2);
    width: max(
      0px,
      min(
        calc((100% - var(--astrbot-chat-sidebar-width, 0px) - var(--astrbot-active-workbench-width, 0px)) * 0.4),
        calc(100% - var(--astrbot-chat-sidebar-width, 0px) - var(--astrbot-active-workbench-width, 0px) - 440px)
      )
    );
    max-width: none;
    transform: translate(-50%, -50%);
    font-size: 0.8125rem;
    text-align: center;
  }
}
</style>
