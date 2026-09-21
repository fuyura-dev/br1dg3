import { useState, useEffect, useCallback } from "react";
import { accessibilityRepairService } from "../services/accessibilityRepairService.js";

export function useAccessibilityStudio() {
  // Application states
  const [status, setStatus] = useState("loading"); // 'idle' | 'loading' | 'success' | 'error'
  const [htmlSource, setHtmlSource] = useState("");
  const [repairedHtml, setRepairedHtml] = useState("");
  const [violations, setViolations] = useState([]);
  const [evaluationMetrics, setEvaluationMetrics] = useState([]);
  const [documentGraph, setDocumentGraph] = useState({ nodes: [], links: [] });

  // Detailed context data keyed by violation ID
  const [sdgContexts, setSdgContexts] = useState({});
  const [repairs, setRepairs] = useState({});

  const [selectedViolationId, setSelectedViolationId] = useState(null);

  // 1. Live Scan: Execute real backend API call when user edits HTML or on extension load
  const runScan = useCallback(async (newHtml) => {
    setStatus("loading");
    setHtmlSource(newHtml);
    setSelectedViolationId(null); // Reset selection on new scan

    try {
      // Trigger the real backend scan via the service
      const result = await accessibilityRepairService.scanHtml(newHtml);
      
      // Update the entire workspace with the live API response
      setViolations(result.violations || []);
      setDocumentGraph(result.documentGraph || { nodes: [], links: [] });
      
      // Assuming the API returns context/repairs keyed by violation ID
      setSdgContexts(result.sdgGraph || {}); 
      setRepairs(result.repairs || {});      
      
      setEvaluationMetrics(result.evaluationMetrics || []);
      setRepairedHtml(result.repairedHtml || newHtml);
      
      setStatus("success");
    } catch (error) {
      console.error("Live scan failed:", error);
      setStatus("error");
    }
  }, []);

  // 2. Initial Load: Check for extension payload or fallback to mock data
  useEffect(() => {
    let isMounted = true;
    
    async function loadWorkspace() {
      try {
        // Check if the Chrome extension passed HTML via localStorage
        const extensionHtml = localStorage.getItem('br1dg3_source_html');
        
        if (extensionHtml) {
          // If launched from the extension, run the real backend scan immediately
          await runScan(extensionHtml);
          
          // Clean up storage so it doesn't affect future direct visits
          localStorage.removeItem('br1dg3_source_html');
        } else {
          // Fallback to mock data for standalone UI testing
          const data = await accessibilityRepairService.getWorkspace();
          if (!isMounted) return;

          setHtmlSource(data.htmlSource);
          setRepairedHtml(data.repairedHtml);
          setViolations(data.violations);
          setEvaluationMetrics(data.evaluationMetrics);
          setDocumentGraph(data.documentGraph);
          setStatus("success");
        }
      } catch (error) {
        console.error("Failed to load workspace:", error);
        if (isMounted) setStatus("error");
      }
    }

    loadWorkspace();
    return () => { isMounted = false; };
  }, [runScan]);

  // 3. Select Violation: Fetch detailed SDG context and repair strategies
  const selectViolation = useCallback(async (violationId) => {
    setSelectedViolationId(violationId);

    // Fetch SDG context if not already loaded in state
    if (violationId && !sdgContexts[violationId]) {
      const context = await accessibilityRepairService.getSdgContext(violationId);
      setSdgContexts(prev => ({ ...prev, [violationId]: context }));
    }

    // Fetch Repair details if not already loaded in state
    if (violationId && !repairs[violationId]) {
      const repair = await accessibilityRepairService.getRepair(violationId);
      setRepairs(prev => ({ ...prev, [violationId]: repair }));
    }
  }, [sdgContexts, repairs]);

  // Derived state for the currently selected violation
  const selectedViolation = violations.find(v => v.id === selectedViolationId) || null;
  const sdgContext = selectedViolationId ? sdgContexts[selectedViolationId] : null;
  const repair = selectedViolationId ? repairs[selectedViolationId] : null;

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
    runScan, // Exported so HtmlEditor can trigger it manually
  };
}