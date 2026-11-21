<template>
  <v-dialog
    :model-value="modelValue"
    max-width="460"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm("conversation.edit") }}
      </v-card-title>
      <v-card-text class="session-edit-fields">
        <v-text-field
          v-model="form.display_name"
          :label="tm('conversation.displayName')"
          variant="outlined"
          density="comfortable"
          hide-details
          autofocus
          @keydown.enter="save"
        />
        <v-select
          v-model="form.project_id"
          :items="projectItems"
          :label="tm('conversation.project')"
          variant="outlined"
          density="comfortable"
          hide-details
        />
        <v-text-field
          v-model="form.workspace_path"
          :label="tm('conversation.workspacePath')"
          :hint="tm('conversation.workspacePathHint')"
          variant="outlined"
          density="comfortable"
          persistent-hint
          clearable
          @keydown.enter="save"
        >
          <template v-if="canPickDirectory" #append-inner>
            <v-btn
              icon
              size="x-small"
              variant="text"
              :title="tm('project.workspace.selectPath')"
              @click.stop="pickWorkspaceDirectory"
            >
              <FolderOpen :size="16" />
            </v-btn>
          </template>
        </v-text-field>
        <v-alert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          density="compact"
        >
          {{ errorMessage }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">
          {{ t("core.common.cancel") }}
        </v-btn>
        <v-btn color="primary" variant="tonal" :loading="saving" @click="save">
          {{ t("core.common.save") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { FolderOpen } from "@lucide/vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { getDesktopRuntimeInfo } from "@/utils/desktopRuntime";
import type { Project } from "@/components/chat/ProjectList.vue";

export interface SessionEditData {
  display_name: string;
  // Empty when the conversation belongs to no project.
  project_id: string;
  // Empty to use the project's or the default workspace.
  workspace_path: string;
}

const props = withDefaults(
  defineProps<{
    modelValue: boolean;
    session: SessionEditData | null;
    projects: Project[];
    saving?: boolean;
    errorMessage?: string;
  }>(),
  { saving: false, errorMessage: "" },
);

const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  save: [data: SessionEditData];
}>();

const { t } = useI18n();
const { tm } = useModuleI18n("features/chat");

const form = ref<SessionEditData>({
  display_name: "",
  project_id: "",
  workspace_path: "",
});
const canPickDirectory = ref(false);

const projectItems = computed(() => [
  { title: tm("conversation.noProject"), value: "" },
  ...props.projects.map((project) => ({
    title: project.title,
    value: project.project_id,
  })),
]);

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return;
    form.value = {
      display_name: props.session?.display_name || "",
      project_id: props.session?.project_id || "",
      workspace_path: props.session?.workspace_path || "",
    };
    const runtimeInfo = await getDesktopRuntimeInfo();
    canPickDirectory.value =
      runtimeInfo.isDesktopRuntime &&
      typeof runtimeInfo.bridge?.pickDirectory === "function";
  },
  { immediate: true },
);

async function pickWorkspaceDirectory() {
  try {
    const selectedPath = await window.astrbotDesktop?.pickDirectory?.(
      form.value.workspace_path || null,
    );
    if (selectedPath) form.value.workspace_path = selectedPath;
  } catch (error) {
    console.warn("[chat-session] Failed to pick workspace directory.", error);
  }
}

function save() {
  emit("save", {
    display_name: form.value.display_name.trim(),
    project_id: form.value.project_id || "",
    // A cleared field is null in Vuetify.
    workspace_path: (form.value.workspace_path || "").trim(),
  });
}
</script>

<style scoped>
.session-edit-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
</style>
