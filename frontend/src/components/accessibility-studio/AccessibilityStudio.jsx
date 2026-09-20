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
    htmlSource,
    repairedHtml,
    violations,
    evaluationMetrics,
    documentGraph,
    selectedViolation,
    sdgContext,
    repair,
    selectViolation,
  } = useAccessibilityStudio();

  const [isGraphOpen, setGraphOpen] = useState(false);

  if (status === "loading") {
    return <div className="accessibility-studio"><p>Loading repair workspace...</p></div>;
  }

  if (status === "error") {
    return <div className="accessibility-studio"><p>Error loading workspace.</p></div>;
  }

  return (
    <div className="accessibility-studio">
      <header className="accessibility-studio__header">
        <h1>BR1DG3 — Accessibility Repair Studio (TESTING MODE)</h1>
      </header>

      <EvaluationSummary metrics={evaluationMetrics} />

      <div className="accessibility-studio__workspace">
        
        <HtmlEditor
          initialHtml={htmlSource}
          isScanning={status === "loading"}
          onRunScan={(newHtml) => {
            console.log("Trigger backend scan here with:", newHtml);
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

      {/* IBINALIK NA ANG TOTOONG DIFF VIEWER (Inalis na ang placeholder) */}
      <DiffViewer 
        original={htmlSource} 
        repaired={repairedHtml} 
      />

      {/* SdgGraphModal */}
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