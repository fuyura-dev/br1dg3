import { useCallback, useEffect, useMemo, useState } from "react";
import { accessibilityRepairService } from "../services/accessibilityRepairService.js";

// Owns all state for the Accessibility Repair Studio: the workspace
// (documents, violations, evaluation metrics) and the current selection
// (which violation is active, and the SDG context/repair that go with
// it). Components receive only the slices they need as props, rather
// than reaching into this hook individually.
export function useAccessibilityStudio() {
  const [status, setStatus] = useState("loading");
  const [htmlSource, setHtmlSource] = useState("");
  const [repairedHtml, setRepairedHtml] = useState("");
  const [violations, setViolations] = useState([]);
  const [evaluationMetrics, setEvaluationMetrics] = useState([]);
  const [documentGraph, setDocumentGraph] = useState({ rootId: null, nodes: [] });

  const [selectedViolationId, setSelectedViolationId] = useState(null);
  const [sdgContext, setSdgContext] = useState(null);
  const [repair, setRepair] = useState(null);

  useEffect(() => {
    let isActive = true;

    accessibilityRepairService
      .getWorkspace()
      .then((workspace) => {
        if (!isActive) return;
        setHtmlSource(workspace.htmlSource);
        setRepairedHtml(workspace.repairedHtml);
        setViolations(workspace.violations);
        setEvaluationMetrics(workspace.evaluationMetrics);
        setDocumentGraph(workspace.documentGraph);
        setSelectedViolationId(workspace.violations[0]?.id ?? null);
        setStatus("ready");
      })
      .catch(() => {
        if (isActive) setStatus("error");
      });

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedViolationId) {
      setSdgContext(null);
      setRepair(null);
      return undefined;
    }

    let isActive = true;

    Promise.all([
      accessibilityRepairService.getSdgContext(selectedViolationId),
      accessibilityRepairService.getRepair(selectedViolationId),
    ]).then(([context, generatedRepair]) => {
      if (!isActive) return;
      setSdgContext(context);
      setRepair(generatedRepair);
    });

    return () => {
      isActive = false;
    };
  }, [selectedViolationId]);

  const selectedViolation = useMemo(
    () => violations.find((violation) => violation.id === selectedViolationId) ?? null,
    [violations, selectedViolationId],
  );

  const selectViolation = useCallback((violationId) => {
    setSelectedViolationId(violationId);
  }, []);

  return {
    status,
    htmlSource,
    repairedHtml,
    violations,
    evaluationMetrics,
    documentGraph,
    selectedViolation,
    sdgContext,
    repair,
    selectViolation,
  };
}
