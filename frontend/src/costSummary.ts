import { getCostSummary, type CostSummary } from "./api";

export type CostSummaryState = {
  summary: CostSummary | null;
  loading: boolean;
  error: unknown | null;
};

// Keep request ownership outside React's render closures. A refresh started by a
// drawer or a completed turn always uses the currently active conversation.
export function createCostSummaryController(onChange: (state: CostSummaryState) => void) {
  let context: { projectId: string; conversationId: string } | null = null;
  let request: AbortController | null = null;
  let state: CostSummaryState = { summary: null, loading: false, error: null };

  function publish(next: CostSummaryState) {
    state = next;
    onChange(next);
  }

  function cancelRequest() {
    const previous = request;
    request = null;
    previous?.abort();
  }

  function dispose() {
    context = null;
    cancelRequest();
  }

  function clear() {
    dispose();
    publish({ summary: null, loading: false, error: null });
  }

  async function refresh() {
    if (!context) return;
    cancelRequest();
    const currentContext = context;
    const currentRequest = new AbortController();
    request = currentRequest;
    publish({ ...state, loading: true, error: null });
    try {
      const summary = await getCostSummary(
        currentContext.projectId,
        currentContext.conversationId,
        currentRequest.signal
      );
      if (context === currentContext && request === currentRequest) {
        request = null;
        publish({ summary, loading: false, error: null });
      }
    } catch (error) {
      if (context === currentContext && request === currentRequest) {
        request = null;
        publish({ ...state, loading: false, error });
      }
    }
  }

  function activate(projectId: string, conversationId: string) {
    clear();
    context = { projectId, conversationId };
    return refresh();
  }

  function accept(summary: CostSummary) {
    if (!context) return;
    // The answer response includes newer ledger data than a refresh that may
    // still be reading the pre-answer summary.
    cancelRequest();
    publish({ summary, loading: false, error: null });
  }

  return { activate, refresh, accept, clear, dispose };
}
