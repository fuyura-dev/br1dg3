import { useState, useEffect, useCallback } from "react";
import { accessibilityRepairService } from "../services/accessibilityRepairService.js";

export function useAccessibilityStudio() {
  // Application states
  const [status, setStatus] = useState("idle"); // 'idle' | 'scanning' | 'repairing' | 'success' | 'error'
  const [htmlSource, setHtmlSource] = useState("");
  const [repairedHtml, setRepairedHtml] = useState("");
  const [violations, setViolations] = useState([]);
  const [evaluationMetrics, setEvaluationMetrics] = useState([]);
  const [documentGraph, setDocumentGraph] = useState({ nodes: [], links: [] });

  // Detailed context data keyed by violation ID
  const [sdgContexts, setSdgContexts] = useState({});
  const [repairs, setRepairs] = useState({});

  const [selectedViolationId, setSelectedViolationId] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // 1. Live Scan: Detect violations and build SDG via /api/graph
  const runScan = useCallback(async (newHtml) => {
    setStatus("scanning");
    setErrorMessage(null);
    setHtmlSource(newHtml);
    setRepairedHtml("");
    setEvaluationMetrics([]);
    setSelectedViolationId(null);

    try {
      const result = await accessibilityRepairService.scanHtml(newHtml);
      const nextViolations = result.violations || [];

      setViolations(nextViolations);
      setDocumentGraph(result.documentGraph || { nodes: [], links: [] });
      setSdgContexts(result.sdgGraph || {});
      setRepairs(result.repairs || {});
      if (nextViolations.length > 0) {
        setSelectedViolationId(nextViolations[0].id);
      }

      setStatus("success");
    } catch (error) {
      console.error("Live scan failed:", error);
      setErrorMessage(error.message || "Failed to connect to the backend API (http://127.0.0.1:8000).");
      setStatus("error");
    }
  }, []);

  // 2. Live Repair: Execute SDG-guided repair and compute evaluation metrics via /api/repair
  const runRepair = useCallback(async (newHtml) => {
    setStatus("repairing");
    setErrorMessage(null);
    setHtmlSource(newHtml);

    try {
      const result = await accessibilityRepairService.repairHtml(newHtml);
      const nextViolations = result.violations || [];

      setViolations(nextViolations);
      setDocumentGraph(result.documentGraph || { nodes: [], links: [] });
      setSdgContexts(result.sdgGraph || {});
      setRepairs(result.repairs || {});
      setEvaluationMetrics(result.evaluationMetrics || []);
      setRepairedHtml(result.repairedHtml || newHtml);
      setSelectedViolationId((prev) => {
        if (prev && nextViolations.some((v) => v.id === prev)) return prev;
        return nextViolations.length > 0 ? nextViolations[0].id : null;
      });

      setStatus("success");
    } catch (error) {
      console.error("Live repair failed:", error);
      setErrorMessage(error.message || "Failed to connect to the backend API (http://127.0.0.1:8000).");
      setStatus("error");
    }
  }, []);

  // 3. Initial Load: Check if the Chrome extension passed HTML via localStorage
  useEffect(() => {
    const extensionHtml = localStorage.getItem("br1dg3_source_html");
    if (extensionHtml) {
      localStorage.removeItem("br1dg3_source_html");
      runScan(extensionHtml);
    }
  }, [runScan]);

  // 4. Select Violation: Fetch detailed SDG context and repair strategies
  const selectViolation = useCallback(async (violationId) => {
    setSelectedViolationId(violationId);

    if (violationId && !sdgContexts[violationId]) {
      const context = await accessibilityRepairService.getSdgContext(violationId);
      setSdgContexts((prev) => ({ ...prev, [violationId]: context }));
    }

    if (violationId && !repairs[violationId]) {
      const repair = await accessibilityRepairService.getRepair(violationId);
      setRepairs((prev) => ({ ...prev, [violationId]: repair }));
    }
  }, [sdgContexts, repairs]);

  // Derived state for the currently selected violation
  const selectedViolation = violations.find((v) => v.id === selectedViolationId) || null;
  const sdgContext = selectedViolationId ? sdgContexts[selectedViolationId] : null;
  const repair = selectedViolationId ? repairs[selectedViolationId] : null;

  return {
    status,
    errorMessage,
    htmlSource,
    repairedHtml,
    violations,
    evaluationMetrics,
    documentGraph,
    selectedViolation,
    sdgContext,
    repair,
    selectViolation,
    runScan,
    runRepair,
  };
}