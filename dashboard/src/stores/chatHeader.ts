import { defineStore } from "pinia";

export const useChatHeaderStore = defineStore("chatHeader", {
  state: () => ({
    title: "",
    subtitle: "",
    // Conversation whose title can be renamed in place; empty elsewhere.
    titleSessionId: "",
    // Name typed in the header, saved by the chat page.
    renameRequest: null as { sessionId: string; title: string } | null,
    projectId: "",
    workspaceFilesOpen: false,
    workbenchWidth: null as number | null,
  }),

  actions: {
    SET_CONTEXT(payload: {
      title?: string;
      subtitle?: string;
      projectId?: string;
      titleSessionId?: string;
    }) {
      const nextProjectId = payload.projectId || "";
      if (this.projectId !== nextProjectId) {
        this.workspaceFilesOpen = false;
      }
      this.title = payload.title || "";
      this.subtitle = payload.subtitle || "";
      this.projectId = nextProjectId;
      this.titleSessionId = payload.titleSessionId || "";
    },
    REQUEST_RENAME(sessionId: string, title: string) {
      this.renameRequest = { sessionId, title };
    },
    TOGGLE_WORKSPACE_FILES() {
      if (this.projectId) {
        this.workspaceFilesOpen = !this.workspaceFilesOpen;
      }
    },
    SET_WORKSPACE_FILES_OPEN(open: boolean) {
      this.workspaceFilesOpen = Boolean(open && this.projectId);
    },
    CLEAR_CONTEXT() {
      this.title = "";
      this.subtitle = "";
      this.projectId = "";
      this.workspaceFilesOpen = false;
      this.titleSessionId = "";
      this.renameRequest = null;
    },
  },
});
