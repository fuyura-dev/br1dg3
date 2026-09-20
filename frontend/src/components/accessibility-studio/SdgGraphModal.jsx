import React, { useEffect, useRef, useState, useMemo } from "react";
// STANDARD IMPORT: Wala nang hacks, ito ang tamang paraan
import ForceGraph2D from "react-force-graph-2d";
import { layoutDocumentTree, layoutRadialGraph } from "../../utils/graphLayout.js";
import { getSeverityMeta } from "../../utils/severity.js";
import '../../styles/SdgGraphModal.css';

// --- Document Tree Graph (Full DOM) ---
function DocumentForceGraph({ documentGraph, violationsById, onSelectViolation }) {
  const graphRef = useRef(null);

  const graphData = useMemo(() => {
    if (!documentGraph?.nodes || documentGraph.nodes.length === 0) return { nodes: [], links: [] };

    const { nodes, edges } = layoutDocumentTree(documentGraph.nodes, documentGraph.rootId);

    return {
      nodes: nodes.map(n => {
        const violation = n.violationId ? violationsById.get(n.violationId) : null;
        // SAFEGUARD: Siguraduhing may valid hex color string na babalik
        const nodeColor = violation ? (getSeverityMeta(violation.severity)?.color || "#ff4d4f") : "#007bff";
        
        return {
          id: String(n.id),
          name: String(n.label || ""),
          violationId: n.violationId,
          val: violation ? 25 : 10,
          color: nodeColor
        };
      }),
      links: edges.map(e => ({
        source: String(e.source || e.from),
        target: String(e.target || e.to)
      }))
    };
  }, [documentGraph, violationsById]);

  useEffect(() => {
    if (graphRef.current) {
      setTimeout(() => graphRef.current.zoomToFit(400, 50), 300);
    }
  }, [graphData]);

  if (!graphData.nodes.length) {
    return (
      <div className="sdg-graph-modal__empty">
        <p>No document structure available yet.</p>
      </div>
    );
  }

  return (
    <ForceGraph2D
      ref={graphRef}
      graphData={graphData}
      nodeLabel="name"
      nodeColor="color"
      nodeVal="val"
      linkColor={() => "#ffffff44"}
      backgroundColor="#1e1e1e"
      onNodeClick={(node) => {
        if (node.violationId) onSelectViolation(node.violationId);
      }}
      dagMode="td" 
      dagLevelDistance={60}
      linkDirectionalArrowLength={3.5}
      linkDirectionalArrowRelPos={1}
    />
  );
}

// --- Radial Graph (Local Context) ---
function RadialForceGraph({ context }) {
  const graphRef = useRef(null);

  const graphData = useMemo(() => {
    if (!context) return { nodes: [], links: [] };

    const { nodes, edges } = layoutRadialGraph(context);

    return {
      nodes: nodes.map(n => ({
        id: String(n.id),
        name: String(n.label || n.id),
        val: n.kind === "target" ? 30 : 15,
        color: n.kind === "target" ? "#ff4d4f" : (n.isFlag ? "#faad14" : "#007bff")
      })),
      links: edges.map(e => ({
        source: String(e.source || e.from),
        target: String(e.target || e.to)
      }))
    };
  }, [context]);

  useEffect(() => {
    if (graphRef.current) {
      setTimeout(() => graphRef.current.zoomToFit(400, 50), 300);
    }
  }, [graphData]);

  if (!graphData.nodes.length) {
    return (
      <div className="sdg-graph-modal__empty">
        <p>No local relationship context found.</p>
      </div>
    );
  }

  return (
    <ForceGraph2D
      ref={graphRef}
      graphData={graphData}
      nodeLabel="name"
      nodeColor="color"
      nodeVal="val"
      linkColor={() => "#ffffff44"}
      backgroundColor="#1e1e1e"
      dagMode="radialout"
      dagLevelDistance={80}
      linkDirectionalArrowLength={3.5}
      linkDirectionalArrowRelPos={1}
    />
  );
}

// --- Main Modal Component ---
function SdgGraphModal({ violation, context, documentGraph, violations, onClose, onSelectViolation }) {
  const [view, setView] = useState(violation ? "local" : "document");
  const closeButtonRef = useRef(null);
  
  const violationsById = useMemo(() => {
    return new Map((violations || []).map((item) => [item.id, item]));
  }, [violations]);

  useEffect(() => {
    closeButtonRef.current?.focus();
    function handleKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="sdg-graph-modal__backdrop" onClick={onClose}>
      <div
        className="sdg-graph-modal"
        role="dialog"
        aria-modal="true"
        aria-label="SDG graph visualizer"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="sdg-graph-modal__header">
          <div className="sdg-graph-modal__title-group">
            <h2>SDG Graph Visualizer</h2>
            <p>{view === "local" ? `Local relationships for ${violation?.id ?? ""}` : "Full document structure"}</p>
          </div>
          
          <div className="sdg-graph-modal__controls">
            <div className="sdg-graph-modal__segmented-control" role="tablist" aria-label="Graph scope">
              <button
                type="button"
                role="tab"
                aria-selected={view === "local"}
                className={`sdg-segmented-btn ${view === "local" ? "active" : ""}`}
                onClick={() => setView("local")}
                disabled={!violation}
              >
                Selected violation
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={view === "document"}
                className={`sdg-segmented-btn ${view === "document" ? "active" : ""}`}
                onClick={() => setView("document")}
              >
                Full document
              </button>
            </div>
            
            <button type="button" className="sdg-graph-modal__close" onClick={onClose} ref={closeButtonRef}>
              Close
            </button>
          </div>
        </header>

        <div className="sdg-graph-modal__canvas-area" style={{ width: '100%', height: '500px', overflow: 'hidden' }}>
          {view === "local" ? (
            violation && context ? (
              <RadialForceGraph context={context} />
            ) : (
              <div className="sdg-graph-modal__empty">
                <p>Select a violation first to see its local relationships.</p>
              </div>
            )
          ) : (
            <DocumentForceGraph
              documentGraph={documentGraph}
              violationsById={violationsById}
              onSelectViolation={(violationId) => {
                onSelectViolation(violationId);
                setView("local");
              }}
            />
          )}
        </div>

        {view === "document" && (
          <footer className="sdg-graph-modal__footer">
            <span className="sdg-indicator-dot"></span>
            Nodes with violations are larger and colored based on severity — click one to inspect.
          </footer>
        )}
      </div>
    </div>
  );
}

export default SdgGraphModal;