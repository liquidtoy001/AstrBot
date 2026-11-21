<template>
  <section class="sidebar-section project-list-shell">
    <div class="sidebar-section-header">
      <button
        type="button"
        class="project-section-toggle"
        :aria-expanded="projectsExpanded"
        @click="projectsExpanded = !projectsExpanded"
      >
        <span>{{ tm("project.title") }}</span>
        <ChevronDown
          v-if="projectsExpanded"
          class="expanded-chevron"
          :size="16"
          aria-hidden="true"
        />
        <ChevronRight v-else :size="16" aria-hidden="true" />
      </button>
      <v-btn
        icon
        size="x-small"
        variant="text"
        class="section-action-btn"
        :title="tm('project.create')"
        @click="$emit('createProject')"
      >
        <Plus :size="18" />
      </v-btn>
    </div>

    <div v-show="projectsExpanded" class="project-list-wrap">
      <div v-if="!projects.length" class="project-list-empty">
        {{ tm("project.noProjects") }}
      </div>
      <!-- A conversation dropped on a project or its list moves into it. -->
      <div
        v-for="project in projects"
        :key="project.project_id"
        @dragover="handleSessionDragOver($event, project.project_id)"
        @dragleave="dropProjectId = null"
        @drop.prevent="handleSessionDrop($event, project.project_id)"
      >
        <div
          class="project-row project-item"
          :class="{
            active: selectedProjectId === project.project_id,
            'drop-target': dropProjectId === project.project_id,
          }"
          role="button"
          tabindex="0"
          @click="handleProjectClick(project)"
          @keydown.enter="handleProjectClick(project)"
          @keydown.space.prevent="handleProjectClick(project)"
          @contextmenu.prevent="openProjectMenu($event, project)"
        >
          <span class="project-title-wrap">
            <span class="project-title">{{ project.title }}</span>
            <ChevronDown
              v-if="isProjectExpanded(project.project_id)"
              :size="16"
              class="project-chevron"
            />
            <ChevronRight v-else :size="16" class="project-chevron" />
          </span>
          <Pin
            v-if="project.pinned"
            class="project-pin-mark"
            :size="13"
            aria-hidden="true"
          />
          <span class="project-actions" @click.stop>
            <v-btn
              icon
              size="x-small"
              variant="text"
              class="project-action-btn"
              :title="tm(project.pinned ? 'actions.unpin' : 'actions.pin')"
              @click="$emit('pinProject', project)"
            >
              <PinOff v-if="project.pinned" :size="15" />
              <Pin v-else :size="15" />
            </v-btn>
            <v-btn
              icon
              size="x-small"
              variant="text"
              class="project-action-btn"
              :title="tm('project.delete')"
              @click="handleDeleteProject(project)"
            >
              <Trash2 :size="15" />
            </v-btn>
          </span>
        </div>

        <Transition name="project-session-fade">
          <div
            v-if="isProjectExpanded(project.project_id)"
            class="project-session-list"
          >
            <div
              v-if="loadingProjectIds.includes(project.project_id)"
              class="project-session-empty"
            >
              {{ tm("project.loadingSessions") }}
            </div>
            <template v-else-if="projectSessionList(project.project_id).length">
              <SidebarSessionRow
                v-for="session in projectSessionList(project.project_id)"
                :key="session.session_id"
                :session-id="session.session_id"
                :title="sessionTitle(session)"
                :active="activeSessionId === session.session_id"
                :running="sessionRunning(session.session_id)"
                :pinned="session.pinned"
                pin-mark
                nested
                @select="$emit('selectSession', session.session_id)"
                @toggle-pin="$emit('pinSession', session)"
                @delete="handleDeleteSession(project.project_id, session)"
                @menu="$emit('sessionMenu', $event, session)"
              />
            </template>
            <div v-else class="project-session-empty">
              {{ tm("project.noSessions") }}
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <ChatContextMenu
      v-model="projectMenuOpen"
      :position="projectMenuPosition"
      :items="projectMenuItems"
      @select="handleProjectMenu"
    />
  </section>
</template>

<script setup lang="ts">
import { chatPreferences } from "@/utils/chatPreferences";
import { computed, ref, watch } from "vue";
import {
  ChevronDown,
  ChevronRight,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Trash2,
} from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import { SESSION_DRAG_TYPE } from "@/composables/useProjects";
import ChatContextMenu from "@/components/chat/ChatContextMenu.vue";
import SidebarSessionRow from "@/components/chat/SidebarSessionRow.vue";

export interface Project {
  project_id: string;
  title: string;
  emoji?: string;
  description?: string;
  workspace_type?: "session" | "project" | "custom";
  workspace_path?: string | null;
  resolved_workspace_path?: string | null;
  shared_memory?: boolean;
  memory_path?: string | null;
  pinned?: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectSession {
  session_id: string;
  display_name?: string | null;
  workspace_path?: string | null;
  pinned?: boolean;
  updated_at: string;
}

interface Props {
  projects: Project[];
  projectSessions: Record<string, ProjectSession[]>;
  loadingProjectIds: string[];
  selectedProjectId?: string | null;
  activeSessionId?: string | null;
  isSessionRunning?: (sessionId: string) => boolean;
}

const props = withDefaults(defineProps<Props>(), {
  selectedProjectId: null,
  activeSessionId: null,
});

const emit = defineEmits<{
  selectProject: [projectId: string];
  createProject: [];
  editProject: [project: Project];
  deleteProject: [projectId: string];
  toggleProject: [projectId: string, expanded: boolean];
  selectSession: [sessionId: string];
  deleteSession: [sessionId: string, projectId: string];
  moveSession: [sessionId: string, projectId: string];
  pinProject: [project: Project];
  pinSession: [session: ProjectSession];
  sessionMenu: [event: MouseEvent, session: ProjectSession];
}>();

const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();

const projectsExpanded = ref(chatPreferences().global.projectsExpanded === true);

watch(projectsExpanded, (expanded) => {
  chatPreferences((preferences) => {
    preferences.global.projectsExpanded = expanded;
  });
});

const expandedProjectIds = ref<Set<string>>(readExpandedProjectIds());

watch(
  () => props.selectedProjectId,
  (projectId) => {
    if (projectId) {
      setProjectExpanded(projectId, true);
    }
  },
);

watch(
  () => props.projects.map((project) => project.project_id).join(","),
  () => {
    const validProjectIds = new Set(
      props.projects.map((project) => project.project_id),
    );
    expandedProjectIds.value.forEach((projectId) => {
      if (validProjectIds.has(projectId)) {
        emit("toggleProject", projectId, true);
      }
    });
  },
  { immediate: true },
);

function readExpandedProjectIds() {
  const ids = chatPreferences().global.expandedProjectIds;
  return new Set<string>(Array.isArray(ids) ? ids.filter((id) => typeof id === "string") : []);
}

function persistExpandedProjectIds() {
  chatPreferences((preferences) => {
    preferences.global.expandedProjectIds = [...expandedProjectIds.value];
  });
}

function isProjectExpanded(projectId: string) {
  return expandedProjectIds.value.has(projectId);
}

function setProjectExpanded(projectId: string, expanded: boolean) {
  const next = new Set(expandedProjectIds.value);
  if (expanded) {
    next.add(projectId);
  } else {
    next.delete(projectId);
  }
  expandedProjectIds.value = next;
  persistExpandedProjectIds();
  emit("toggleProject", projectId, expanded);
}

// The project a dragged conversation is currently over.
const dropProjectId = ref<string | null>(null);

function handleSessionDragOver(event: DragEvent, projectId: string) {
  if (!event.dataTransfer?.types.includes(SESSION_DRAG_TYPE)) return;
  event.preventDefault();
  dropProjectId.value = projectId;
}

function handleSessionDrop(event: DragEvent, projectId: string) {
  dropProjectId.value = null;
  const sessionId = event.dataTransfer?.getData(SESSION_DRAG_TYPE);
  if (sessionId) emit("moveSession", sessionId, projectId);
}

// The project whose right-click menu is open.
const menuProject = ref<Project | null>(null);
const projectMenuOpen = ref(false);
const projectMenuPosition = ref<[number, number]>([0, 0]);
const projectMenuItems = computed(() => [
  { key: "edit", title: tm("project.edit"), icon: Pencil },
  {
    key: "pin",
    title: tm(menuProject.value?.pinned ? "actions.unpin" : "actions.pin"),
    icon: menuProject.value?.pinned ? PinOff : Pin,
  },
  { key: "delete", title: tm("project.delete"), icon: Trash2, danger: true },
]);

function openProjectMenu(event: MouseEvent, project: Project) {
  menuProject.value = project;
  projectMenuPosition.value = [event.clientX, event.clientY];
  projectMenuOpen.value = true;
}

function handleProjectMenu(key: string) {
  const project = menuProject.value;
  if (!project) return;
  if (key === "edit") emit("editProject", project);
  if (key === "pin") emit("pinProject", project);
  if (key === "delete") void handleDeleteProject(project);
}

function handleProjectClick(project: Project) {
  const nextExpanded = !isProjectExpanded(project.project_id);
  setProjectExpanded(project.project_id, nextExpanded);
  emit("selectProject", project.project_id);
}

function projectSessionList(projectId: string) {
  return props.projectSessions[projectId] || [];
}

function sessionRunning(sessionId: string) {
  return props.isSessionRunning?.(sessionId) || false;
}

function sessionTitle(session: ProjectSession) {
  return session.display_name?.trim() || tm("conversation.newConversation");
}

async function handleDeleteProject(project: Project) {
  const message = tm("project.confirmDelete", { title: project.title });
  if (await askForConfirmation(message, confirmDialog)) {
    emit("deleteProject", project.project_id);
  }
}

async function handleDeleteSession(projectId: string, session: ProjectSession) {
  const message = tm("conversation.confirmDelete", {
    name: sessionTitle(session),
  });
  if (await askForConfirmation(message, confirmDialog)) {
    emit("deleteSession", session.session_id, projectId);
  }
}

</script>

<style scoped>
.project-list-shell {
  margin-top: 2px;
}

.sidebar-section-header {
  min-height: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  color: var(--chat-section-label);
  font-size: 12px;
  font-weight: 500;
}

.project-section-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 36px;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.project-section-toggle:hover {
  color: rgb(var(--v-theme-on-surface));
}

.project-section-toggle .expanded-chevron {
  opacity: 0;
}

.project-section-toggle:hover .expanded-chevron,
.project-section-toggle:focus-visible .expanded-chevron {
  opacity: 1;
}

.section-action-btn,
.project-action-btn {
  color: var(--chat-muted);
}

.section-action-btn :deep(svg),
.project-action-btn :deep(svg),
.project-chevron {
  flex: 0 0 auto;
  stroke-width: 2;
}

.section-action-btn {
  width: 36px;
  height: 36px;
  min-width: 36px;
}

.section-action-btn:hover,
.project-action-btn:hover {
  color: rgb(var(--v-theme-on-surface));
}

.project-list-wrap,
.project-session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-row {
  width: 100%;
  min-height: 30px;
  border: 0;
  border-radius: var(--astrbot-radius-navigation);
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 10px;
  position: relative;
  box-sizing: border-box;
  cursor: pointer;
  text-align: left;
}

.project-row:hover {
  background: var(--chat-session-active-bg);
}

.project-row:hover,
.project-row:focus-within {
  padding-right: 56px;
}

.project-row.active {
  background: var(--chat-session-selected-bg);
}

.project-row.drop-target {
  background: var(--chat-session-active-bg);
  outline: 1px dashed rgba(var(--v-theme-primary), 0.7);
  outline-offset: -1px;
}

.project-title-wrap {
  min-width: 0;
  flex: 1;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.project-title {
  min-width: 0;
  flex: 0 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.project-chevron,
.project-pin-mark {
  flex: 0 0 auto;
  color: var(--chat-muted);
}

.project-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  visibility: hidden;
}

.project-row:hover .project-actions,
.project-row:focus-within .project-actions {
  visibility: visible;
}

.project-row:hover .project-pin-mark,
.project-row:focus-within .project-pin-mark {
  visibility: hidden;
}

.project-session-list {
  padding: 0 0 6px 12px;
}

.project-session-fade-enter-active {
  transition: opacity 0.1s ease-out;
}

.project-session-fade-leave-active {
  transition: opacity 0.08s ease-in;
}

.project-session-fade-enter-from,
.project-session-fade-leave-to {
  opacity: 0;
}

.project-list-empty,
.project-session-empty {
  padding: 5px 10px;
  color: var(--chat-muted);
  font-size: 13px;
}
</style>
