import React, { useState } from "react";
import ReactDiffViewer from "react-diff-viewer-continued";
import "../../styles/DiffViewer.css";

function DiffViewer({ original, repaired }) {
  const [copyState, setCopyState] = useState("idle");

  // SAFETY: Siguraduhing purong string ang ipinapasa para hindi mag-error ang React
  const safeOriginal = typeof original === "string" ? original : String(original || "");
  const safeRepaired = typeof repaired === "string" ? repaired : String(repaired || "");

  async function handleCopy() {
    if (!safeRepaired) return;
    try {
      await navigator.clipboard.writeText(safeRepaired);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    } finally {
      setTimeout(() => setCopyState("idle"), 1500);
    }
  }

  // Huwag i-render kung wala pang laman ang original o repaired HTML
  if (!safeOriginal || !safeRepaired) return null;

  return (
    <section className="diff-viewer" aria-label="Original and repaired HTML comparison">
      <header className="diff-viewer__header">
        <h2>{"Repair (SDG-Guided) \u2014 Side-by-Side Diff"}</h2>
        <div className="diff-viewer__controls">
          <button type="button" className="diff-viewer__copy" onClick={handleCopy} disabled={!safeRepaired}>
            {copyState === "copied" ? "Copied!" : copyState === "error" ? "Copy failed" : "Copy Repaired HTML"}
          </button>
        </div>
      </header>

      <div className="diff-viewer__container">
        <ReactDiffViewer
          oldValue={safeOriginal}
          newValue={safeRepaired}
          splitView={true}
          useDarkTheme={true}
          leftTitle="Original HTML"
          rightTitle="Repaired HTML"
        />
      </div>
    </section>
  );
}

export default DiffViewer;