import { defineStore } from "pinia";

export const useChatHeaderStore = defineStore("chatHeader", {
  state: () => ({
    title: "",
    subtitle: "",
    projectId: "",
    workspaceFilesOpen: false,
    workbenchWidth: null as number | null,
    sessionPanelOpen: false,
    // The ChatUI settings dialog opens the header's update and account
    // dialogs through this request; the header shows them and clears it.
    updateAvailable: false,
    headerDialog: "" as "" | "update" | "account",
    // Double-clicking the header title asks the chat page to rename the
    // current conversation with its usual dialog.
    titleRenamable: false,
    renameRequested: false,
  }),

  actions: {
    SET_CONTEXT(payload: {
      title?: string;
      subtitle?: string;
      projectId?: string;
      titleRenamable?: boolean;
    }) {
      const nextProjectId = payload.projectId || "";
      if (this.projectId !== nextProjectId) {
        this.workspaceFilesOpen = false;
      }
      this.title = payload.title || "";
      this.subtitle = payload.subtitle || "";
      this.projectId = nextProjectId;
      this.titleRenamable = Boolean(payload.titleRenamable);
    },
    TOGGLE_WORKSPACE_FILES() {
      if (this.projectId) {
        this.workspaceFilesOpen = !this.workspaceFilesOpen;
      }
    },
    SET_WORKSPACE_FILES_OPEN(open: boolean) {
      this.workspaceFilesOpen = Boolean(open && this.projectId);
    },
    SET_SESSION_PANEL_OPEN(open: boolean) {
      this.sessionPanelOpen = Boolean(open);
    },
    OPEN_HEADER_DIALOG(dialog: "update" | "account") {
      this.headerDialog = dialog;
    },
    REQUEST_RENAME() {
      if (this.titleRenamable) this.renameRequested = true;
    },
    CLEAR_CONTEXT() {
      this.titleRenamable = false;
      this.title = "";
      this.subtitle = "";
      this.projectId = "";
      this.workspaceFilesOpen = false;
      this.sessionPanelOpen = false;
    },
  },
});
