import { useMemo, useState } from "react";
import { diffLines } from "../../utils/diff.js";
import "./DiffViewer.css";

function DiffLine({ lineNumber, text, changeType, highlight, isFocused }) {
  if (text === null || text === undefined) {
    return (
      <div className="diff-line diff-line--empty" aria-hidden="true">
        {"\u00A0"}
      </div>
    );
  }

  const classes = ["diff-line"];
  if (highlight && changeType) classes.push(`diff-line--${changeType}`);
  if (isFocused) classes.push("diff-line--focused");

  return (
    <div className={classes.join(" ")}>
      <span className="diff-line__number">{lineNumber}</span>
      <span className="diff-line__text">{text.length ? text : "\u00A0"}</span>
    </div>
  );
}

function DiffViewer({ original, repaired, focusLine }) {
  const [highlightChanges, setHighlightChanges] = useState(true);
  const [copyState, setCopyState] = useState("idle");

  const rows = useMemo(() => diffLines(original, repaired), [original, repaired]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(repaired);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    } finally {
      setTimeout(() => setCopyState("idle"), 1500);
    }
  }

  return (
    <section className="diff-viewer" aria-label="Original and repaired HTML comparison">
      <header className="diff-viewer__header">
        <h2>{"Repair (SDG-Guided) \u2014 Side-by-Side Diff"}</h2>
        <div className="diff-viewer__controls">
          <label className="diff-viewer__toggle">
            <input
              type="checkbox"
              checked={highlightChanges}
              onChange={(event) => setHighlightChanges(event.target.checked)}
            />
            Highlight changes
          </label>
          <button type="button" className="diff-viewer__copy" onClick={handleCopy}>
            {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy Repaired HTML"}
          </button>
        </div>
      </header>

      <div className="diff-viewer__grid">
        <div className="diff-viewer__column">
          <h3>Original HTML</h3>
          <pre className="diff-viewer__code">
            {rows.map((row, index) => (
              <DiffLine
                key={index}
                lineNumber={row.originalLine}
                text={row.originalText}
                changeType={row.type === "removed" ? "removed" : row.type === "unchanged" ? "unchanged" : null}
                highlight={highlightChanges}
                isFocused={row.originalLine === focusLine}
              />
            ))}
          </pre>
        </div>
        <div className="diff-viewer__column">
          <h3>Repaired HTML</h3>
          <pre className="diff-viewer__code">
            {rows.map((row, index) => (
              <DiffLine
                key={index}
                lineNumber={row.revisedLine}
                text={row.revisedText}
                changeType={row.type === "added" ? "added" : row.type === "unchanged" ? "unchanged" : null}
                highlight={highlightChanges}
                isFocused={false}
              />
            ))}
          </pre>
        </div>
      </div>
    </section>
  );
}

export default DiffViewer;
