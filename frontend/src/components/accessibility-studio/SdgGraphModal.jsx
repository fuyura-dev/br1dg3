import React, { useEffect, useRef, useState, useMemo } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { layoutDocumentTree, layoutRadialGraph } from "../../utils/graphLayout.js";
import { getSeverityMeta } from "../../utils/severity.js";
import '../../styles/SdgGraphModal.css';

// Helper function para i-render ang text label sa mga graph edges
const drawEdgeLabel = (link, ctx) => {
  if (!link.relation) return;
  const start = link.source;
  const end = link.target;
  
  // Huwag i-render kung hindi pa na-compute ng physics engine ang x/y coordinates
  if (typeof start !== 'object' || typeof end !== 'object') return;

  const textPos = {
    x: start.x + (end.x - start.x) / 2,
    y: start.y + (end.y - start.y) / 2
  };
  
  const relLink = { x: end.x - start.x, y: end.y - start.y };
  let textAngle = Math.atan2(relLink.y, relLink.x);
  
  // Panatilihing nakatayo ang text kahit umikot ang node
  if (textAngle > Math.PI / 2) textAngle = -(Math.PI - textAngle);
  if (textAngle < -Math.PI / 2) textAngle = -(-Math.PI - textAngle);

  const fontSize = 3.5;
  ctx.font = `${fontSize}px Sans-Serif`;
  const textWidth = ctx.measureText(link.relation).width;
  const bgDimensions = [textWidth + 2, fontSize + 2];

  ctx.save();
  ctx.translate(textPos.x, textPos.y);
  ctx.rotate(textAngle);

  // Background ng label
  ctx.fillStyle = 'rgba(30, 30, 30, 0.85)';
  ctx.fillRect(-bgDimensions[0] / 2, -bgDimensions[1] / 2, bgDimensions[0], bgDimensions[1]);

  // Text ng label
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#a1e3b6';
  ctx.fillText(link.relation, 0, 0);
  ctx.restore();
};

function DocumentForceGraph({ documentGraph, violationsById, onSelectViolation }) {
  const graphRef = useRef(null);

  const graphData = useMemo(() => {
    // Ipasa ang buong documentGraph object sa halip na nodes lang
    const { nodes, links } = layoutDocumentTree(documentGraph);

    return {
      nodes: nodes.map(n => {
        const violation = n.violationId ? violationsById.get(n.violationId) : null;
        return {
          ...n,
          name: n.label,
          val: violation ? 25 : 10,
          color: violation ? getSeverityMeta(violation.impact || violation.severity)?.color : "#007bff"
        };
      }),
      links
    };
  }, [documentGraph, violationsById]);

  useEffect(() => {
    if (graphRef.current) setTimeout(() => graphRef.current.zoomToFit(400, 50), 300);
  }, [graphData]);

  if (!graphData.nodes.length) return <div className="sdg-graph-modal__empty"><p>No document structure available.</p></div>;

  return (
    <ForceGraph2D
      ref={graphRef}
      graphData={graphData}
      nodeLabel="name"
      nodeColor="color"
      nodeVal="val"
      linkColor={() => "#ffffff44"}
      backgroundColor="#1e1e1e"
      linkDirectionalArrowLength={3.5}
      linkDirectionalArrowRelPos={1}
      linkCanvasObjectMode={() => 'after'}
      linkCanvasObject={drawEdgeLabel}
      onNodeClick={(node) => { if (node.violationId) onSelectViolation(node.violationId); }}
      dagMode="td" 
      dagLevelDistance={60}
    />
  );
}

function RadialForceGraph({ context }) {
  const graphRef = useRef(null);

  const graphData = useMemo(() => {
    const { nodes, links } = layoutRadialGraph(context);

    return {
      nodes: nodes.map(n => ({
        ...n,
        name: n.label,
        val: n.kind === "target" ? 30 : 15,
        color: n.kind === "target" ? "#ff4d4f" : (n.isFlag ? "#faad14" : "#007bff")
      })),
      links
    };
  }, [context]);

  useEffect(() => {
    if (graphRef.current) setTimeout(() => graphRef.current.zoomToFit(400, 50), 300);
  }, [graphData]);

  if (!graphData.nodes.length) return <div className="sdg-graph-modal__empty"><p>No local context found.</p></div>;

  return (
    <ForceGraph2D
      ref={graphRef}
      graphData={graphData}
      nodeLabel="name"
      nodeColor="color"
      nodeVal="val"
      linkColor={() => "#ffffff44"}
      backgroundColor="#1e1e1e"
      linkDirectionalArrowLength={3.5}
      linkDirectionalArrowRelPos={1}
      linkCanvasObjectMode={() => 'after'}
      linkCanvasObject={drawEdgeLabel}
      dagMode="radialout"
      dagLevelDistance={80}
    />
  );
}

function SdgGraphModal({ violation, context, documentGraph, violations, onClose, onSelectViolation }) {
  const [view, setView] = useState(violation ? "local" : "document");
  const closeButtonRef = useRef(null);
  
  const violationsById = useMemo(() => new Map((violations || []).map(v => [v.id, v])), [violations]);

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div className="sdg-graph-modal__backdrop" onClick={onClose}>
      <div className="sdg-graph-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <header className="sdg-graph-modal__header">
          <div className="sdg-graph-modal__title-group">
            <h2>SDG Graph Visualizer</h2>
            <p>{view === "local" ? `Local relationships for ${violation?.id ?? ""}` : "Full document structure"}</p>
          </div>
          <div className="sdg-graph-modal__controls">
            <div className="sdg-graph-modal__segmented-control" role="tablist">
              <button role="tab" className={`sdg-segmented-btn ${view === "local" ? "active" : ""}`} onClick={() => setView("local")} disabled={!violation}>Selected violation</button>
              <button role="tab" className={`sdg-segmented-btn ${view === "document" ? "active" : ""}`} onClick={() => setView("document")}>Full document</button>
            </div>
            <button className="sdg-graph-modal__close" onClick={onClose} ref={closeButtonRef}>Close</button>
          </div>
        </header>

        <div className="sdg-graph-modal__canvas-area" style={{ width: '100%', height: '100%', overflow: 'hidden' }}>
          {view === "local" ? (
            violation && context ? <RadialForceGraph context={context} /> : <div className="sdg-graph-modal__empty"><p>Select a violation first.</p></div>
          ) : (
            <DocumentForceGraph documentGraph={documentGraph} violationsById={violationsById} onSelectViolation={(vId) => { onSelectViolation(vId); setView("local"); }} />
          )}
        </div>
      </div>
    </div>
  );
}

export default SdgGraphModal;