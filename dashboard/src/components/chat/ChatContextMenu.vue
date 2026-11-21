<template>
  <v-menu
    :model-value="modelValue"
    :target="position"
    location="bottom start"
    :close-on-content-click="false"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-list density="compact" class="chat-context-menu">
      <template v-for="item in items" :key="item.key">
        <v-list-item v-if="item.children" :title="item.title">
          <template #prepend>
            <component :is="item.icon" :size="16" class="chat-context-icon" />
          </template>
          <template #append>
            <ChevronRight :size="14" />
          </template>
          <v-menu activator="parent" submenu open-on-hover location="end">
            <v-list density="compact" class="chat-context-menu">
              <v-list-item
                v-for="child in item.children"
                :key="child.key"
                :title="child.title"
                @click="choose(child.key)"
              />
            </v-list>
          </v-menu>
        </v-list-item>
        <v-list-item
          v-else
          :title="item.title"
          :class="{ 'text-error': item.danger }"
          @click="choose(item.key)"
        >
          <template #prepend>
            <component :is="item.icon" :size="16" class="chat-context-icon" />
          </template>
        </v-list-item>
      </template>
    </v-list>
  </v-menu>
</template>

<script setup lang="ts">
import type { Component } from "vue";
import { ChevronRight } from "@lucide/vue";

export interface ChatContextMenuItem {
  key: string;
  title: string;
  icon?: Component;
  danger?: boolean;
  // Entries of a submenu; the item itself is then not selectable.
  children?: { key: string; title: string }[];
}

// Menu opened at the pointer by a right-click in the chat sidebar.
defineProps<{
  modelValue: boolean;
  // Viewport coordinates of the right-click.
  position: [number, number];
  items: ChatContextMenuItem[];
}>();

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  select: [key: string];
}>();

function choose(key: string) {
  emit("update:modelValue", false);
  emit("select", key);
}
</script>

<style scoped>
.chat-context-menu {
  min-width: 168px;
}

.chat-context-icon {
  margin-right: 10px;
}
</style>
