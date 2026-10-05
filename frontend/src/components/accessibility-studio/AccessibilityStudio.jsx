import { useState } from "react";
import { useNavigate } from "react-router-dom";
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
  const navigate = useNavigate();
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
    <div className="studio-page-wrapper">
      <div className="accessibility-studio">
      <header className="accessibility-studio__header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <img className="br1dg3-logo" src="/BR1DG3 - Logo.png" alt="BR1DG3 Logo" style={{ width: '40px', height: '40px', objectFit: 'contain' }} />
          <h1 style={{ margin: 0 }}>BR1DG3 — Accessibility Repair Studio</h1>
        </div>
        
        <button 
          className="accessibility-studio__back-btn"
          onClick={() => navigate('/')}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"></line>
            <polyline points="12 19 5 12 12 5"></polyline>
          </svg>
          Back to Landing
        </button>
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

      <DiffViewer 
        original={htmlSource} 
        repaired={repairedHtml} 
      />

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
    </div>
  );
}

export default AccessibilityStudio;