import { useState } from "react";
import { useAccessibilityStudio } from "../../hooks/useAccessibilityStudio.js";
import HtmlEditor from "./HtmlEditor.jsx";
import ViolationsPanel from "./ViolationsPanel.jsx";
import SdgContextPanel from "./SdgContextPanel.jsx";
import SdgGraphModal from "./SdgGraphModal.jsx";
import RepairSummary from "./RepairSummary.jsx";
import DiffViewer from "./DiffViewer.jsx";
import EvaluationSummary from "./EvaluationSummary.jsx";
import "./AccessibilityStudio.css";

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
    return (
      <div className="accessibility-studio accessibility-studio--message">
        <p>{"Loading repair workspace\u2026"}</p>
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="accessibility-studio accessibility-studio--message">
        <p>The repair workspace could not be loaded.</p>
      </div>
    );
  }

  return (
    <div className="accessibility-studio">
      <header className="accessibility-studio__header">
        <h1>{"BR1DG3 \u2014 Accessibility Repair Studio"}</h1>
        <p>SDG-guided repair analysis workspace</p>
      </header>

      <EvaluationSummary metrics={evaluationMetrics} />

      <div className="accessibility-studio__workspace">
        <HtmlEditor
          title="HTML Editor (Original)"
          code={htmlSource}
          highlightedLine={selectedViolation?.line ?? null}
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

      <DiffViewer original={htmlSource} repaired={repairedHtml} focusLine={selectedViolation?.line ?? null} />

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
