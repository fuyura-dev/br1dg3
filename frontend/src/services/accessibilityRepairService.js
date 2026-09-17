import {
  htmlSource,
  repairedHtml,
  violations,
  sdgGraph,
  documentGraph,
  repairs,
  evaluationMetrics,
} from "../data/accessibilityStudioData.js";

// This is the seam where the BR1DG3 backend/LLM pipeline will eventually
// connect. Every method here currently resolves against local mock data,
// but each is already shaped like an API call (async, keyed lookups) so
// that swapping the bodies for real `fetch()` calls later does not
// require touching the hook or any component.
export const accessibilityRepairService = {
  async getWorkspace() {
    return {
      htmlSource,
      repairedHtml,
      violations,
      evaluationMetrics,
      documentGraph,
    };
  },

  async getSdgContext(violationId) {
    return sdgGraph[violationId] ?? null;
  },

  async getRepair(violationId) {
    return repairs[violationId] ?? null;
  },
};
