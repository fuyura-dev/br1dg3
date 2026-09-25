import React, { useState, useMemo } from "react";
import { DiffEditor } from "@monaco-editor/react";
import { formatHtmlForDiff } from "../../utils/diff.js";
import "../../styles/DiffViewer.css";

function DiffViewer({ original, repaired }) {
  const [copyState, setCopyState] = useState("idle");
  const [normalizeFormat, setNormalizeFormat] = useState(true);
  const [splitView, setSplitView] = useState(true);

  const safeOriginal = typeof original === "string" ? original : String(original || "");
  const safeRepaired = typeof repaired === "string" ? repaired : String(repaired || "");

  const { displayOriginal, displayRepaired } = useMemo(() => {
    if (!normalizeFormat) {
      return { displayOriginal: safeOriginal, displayRepaired: safeRepaired };
    }
    return {
      displayOriginal: formatHtmlForDiff(safeOriginal),
      displayRepaired: formatHtmlForDiff(safeRepaired),
    };
  }, [safeOriginal, safeRepaired, normalizeFormat]);

  async function handleCopy() {
    if (!safeRepaired) return;
    try {
      await navigator.clipboard.writeText(normalizeFormat ? displayRepaired : safeRepaired);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    } finally {
      setTimeout(() => setCopyState("idle"), 1500);
    }
  }

  if (!safeOriginal || !safeRepaired) return null;

  return (
    <section className="diff-viewer" aria-label="Original and repaired HTML comparison">
      <header className="diff-viewer__header">
        <div>
          <h2>{"Repair (SDG-Guided) \u2014 Original vs. Repaired HTML"}</h2>
        </div>
        <div className="diff-viewer__controls">
          <label className="diff-viewer__toggle">
            <input
              type="checkbox"
              checked={normalizeFormat}
              onChange={(e) => setNormalizeFormat(e.target.checked)}
            />
            <span>Normalize Formatting</span>
          </label>
          <label className="diff-viewer__toggle">
            <input
              type="checkbox"
              checked={splitView}
              onChange={(e) => setSplitView(e.target.checked)}
            />
            <span>Side-by-Side</span>
          </label>
          <button
            type="button"
            className="diff-viewer__copy"
            onClick={handleCopy}
            disabled={!safeRepaired}
          >
            {copyState === "copied"
              ? "Copied!"
              : copyState === "error"
              ? "Copy failed"
              : "Copy Repaired HTML"}
          </button>
        </div>
      </header>

      {splitView && (
        <div className="diff-viewer__labels" aria-hidden="true">
          <span>Original HTML</span>
          <span>Repaired HTML</span>
        </div>
      )}

      <div className="diff-viewer__container">
        <DiffEditor
          height="500px"
          language="html"
          theme="vs-dark"
          original={displayOriginal}
          modified={displayRepaired}
          options={{
            readOnly: true,
            renderSideBySide: splitView,
            ignoreTrimWhitespace: true,
            renderIndicators: true,
            originalEditable: false,
            diffWordWrap: "on",
            wordWrap: "on",
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
            lineHeight: 20,
          }}
        />
      </div>
    </section>
  );
}

export default DiffViewer;