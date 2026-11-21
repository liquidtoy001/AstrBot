<template>
  <div
    class="session-row"
    :class="{ active, running, nested }"
    role="button"
    tabindex="0"
    draggable="true"
    @dragstart="$event.dataTransfer?.setData(SESSION_DRAG_TYPE, sessionId)"
    @click="emit('select')"
    @keydown.enter="emit('select')"
    @keydown.space.prevent="emit('select')"
    @contextmenu.prevent="emit('menu', $event)"
  >
    <span class="session-row-title">{{ title }}</span>
    <span v-if="note" class="session-row-note">{{ note }}</span>
    <Pin
      v-if="pinned && pinMark"
      class="session-row-pin-mark"
      :size="13"
      aria-hidden="true"
    />
    <div class="session-row-actions" @click.stop>
      <v-btn
        icon
        size="x-small"
        variant="text"
        class="session-row-action"
        :title="tm(pinned ? 'actions.unpin' : 'actions.pin')"
        @click="emit('togglePin')"
      >
        <PinOff v-if="pinned" :size="15" />
        <Pin v-else :size="15" />
      </v-btn>
      <v-btn
        icon
        size="x-small"
        variant="text"
        class="session-row-action"
        :title="tm('actions.deleteChat')"
        @click="emit('delete')"
      >
        <Trash2 :size="15" />
      </v-btn>
    </div>
    <v-progress-circular
      v-if="running"
      class="session-row-progress"
      indeterminate
      size="16"
      width="2"
    />
  </div>
</template>

<script setup lang="ts">
import { Pin, PinOff, Trash2 } from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";
import { SESSION_DRAG_TYPE } from "@/composables/useProjects";

// One conversation in the chat sidebar: in the pinned list, in the
// conversation list and inside a project.
withDefaults(
  defineProps<{
    sessionId: string;
    title: string;
    active?: boolean;
    running?: boolean;
    pinned?: boolean;
    // Show a pin next to the title; off where the list itself says "pinned".
    pinMark?: boolean;
    // Inside a project: smaller text under the project's name.
    nested?: boolean;
    // Muted text after the title, such as the project of a pinned conversation.
    note?: string;
  }>(),
  {
    active: false,
    running: false,
    pinned: false,
    pinMark: false,
    nested: false,
    note: "",
  },
);

const emit = defineEmits<{
  select: [];
  togglePin: [];
  delete: [];
  menu: [event: MouseEvent];
}>();

const { tm } = useModuleI18n("features/chat");
</script>

<style scoped>
.session-row {
  width: 100%;
  min-height: 30px;
  border-radius: var(--astrbot-radius-navigation);
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 10px;
  position: relative;
  box-sizing: border-box;
  cursor: pointer;
}

.session-row:hover {
  background: var(--chat-session-active-bg);
}

.session-row.active {
  background: var(--chat-session-selected-bg);
}

.session-row.running {
  padding-right: 27px;
}

.session-row:hover,
.session-row:focus-within {
  padding-right: 56px;
}

.session-row-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.session-row.nested .session-row-title {
  font-size: 13px;
  font-weight: 400;
}

.session-row-note {
  flex: 0 1 auto;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--chat-muted);
  font-size: 12px;
}

.session-row-pin-mark {
  flex: 0 0 auto;
  color: var(--chat-muted);
}

.session-row-progress {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  flex-shrink: 0;
}

.session-row-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  visibility: hidden;
}

.session-row:hover .session-row-actions,
.session-row:focus-within .session-row-actions {
  visibility: visible;
}

.session-row:hover .session-row-progress,
.session-row:focus-within .session-row-progress,
.session-row:hover .session-row-pin-mark,
.session-row:focus-within .session-row-pin-mark,
.session-row:hover .session-row-note,
.session-row:focus-within .session-row-note {
  visibility: hidden;
}

.session-row-action {
  color: var(--chat-muted);
}

.session-row-action:hover {
  color: rgb(var(--v-theme-on-surface));
}
</style>
