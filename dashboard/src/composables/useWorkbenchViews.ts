import { ref } from "vue";
import { fetchWithAuth } from "@/api/http";
import type { WorkbenchView } from "@/utils/chatViews";

// One catalog of launcher views shared by the workbench and its "New workbench"
// tab, so both read the same request instead of fetching it twice.
const views = ref<WorkbenchView[]>([]);
const loading = ref(false);
const failed = ref(false);
let pending: Promise<void> | null = null;

/** Shared state of the workbench view catalog.
 *
 * Returns:
 *     The catalog refs and `load`, which refetches the list; calls made
 *     while a request is in flight share that request.
 */
export function useWorkbenchViews() {
  function load() {
    pending ||= (async () => {
      loading.value = true;
      failed.value = false;
      try {
        const response = await fetchWithAuth("/api/v1/chat/workbench/views");
        if (!response.ok) throw new Error("Workbench catalog unavailable");
        views.value = (await response.json()).data;
      } catch {
        failed.value = true;
      } finally {
        loading.value = false;
        pending = null;
      }
    })();
    return pending;
  }
  return { views, loading, failed, load };
}
