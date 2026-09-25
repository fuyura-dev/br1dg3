import { useState } from "react";
import { useAccessibilityStudio } from "../../hooks/useAccessibilityStudio.js";

import HtmlEditor from "./HtmlEditor.jsx";
import SdgGraphModal from "./SdgGraphModal.jsx";
import DiffViewer from "./DiffViewer.jsx";

import ViolationsPanel from "./ViolationsPanel.jsx";
import SdgContextPanel from "./SdgContextPanel.jsx";
import RepairSummary from "./RepairSummary.jsx";
import EvaluationSummary from "./EvaluationSummary.jsx";
import '../../styles/AccessibilityStudio.css';

function AccessibilityStudio() {
  const {
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
  } = useAccessibilityStudio();

  const [isGraphOpen, setGraphOpen] = useState(false);

  return (
    <div className="accessibility-studio">
      <header className="accessibility-studio__header">
        <h1>BR1DG3 — Accessibility Repair Studio</h1>
      </header>

      {errorMessage && (
        <div role="alert" style={{ padding: "12px 16px", marginBottom: "16px", borderRadius: "8px", backgroundColor: "rgba(220, 38, 38, 0.15)", color: "#fca5a5", border: "1px solid rgba(220, 38, 38, 0.4)" }}>
          {errorMessage}
        </div>
      )}

      <EvaluationSummary metrics={evaluationMetrics} />

      <div className="accessibility-studio__workspace">
        
        <HtmlEditor
          initialHtml={htmlSource}
          isScanning={status === "scanning"}
          isRepairing={status === "repairing"}
          onRunScan={(newHtml) => {
            runScan(newHtml);
          }}
          onRunRepair={(newHtml) => {
            runRepair(newHtml);
          }}
        />

        <ViolationsPanel
          violations={violations}
          selectedId={selectedViolation?.id ?? null}
          onSelect={selectViolation}
        />
        <SdgContextPanel
          violation={selectedViolation}
          context={sdgContext}
          onOpenGraph={() => setGraphOpen(true)}
        />
      </div>

      <RepairSummary violation={selectedViolation} repair={repair} />

      {/* Side-by-side comparison of the original and repaired HTML */}
      <DiffViewer 
        original={htmlSource} 
        repaired={repairedHtml} 
      />

      {/* SDG Graph Visualizer Modal */}
      {isGraphOpen && (
        <SdgGraphModal
          violation={selectedViolation}
          context={sdgContext}
          documentGraph={documentGraph}
          violations={violations}
          onClose={() => setGraphOpen(false)}
          onSelectViolation={selectViolation}
        />
      )}

    </div>
  );
}

export default AccessibilityStudio;