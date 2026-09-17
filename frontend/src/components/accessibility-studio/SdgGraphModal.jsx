import { useEffect, useRef, useState, useCallback } from "react";
import { layoutDocumentTree, layoutRadialGraph } from "../../utils/graphLayout.js";
import { getSeverityMeta } from "../../utils/severity.js";
import "./SdgGraphModal.css";

// --- Configuration Constants ---
const TREE_X_SPACING = 160;
const TREE_Y_SPACING = 80;
const TREE_PADDING = 80;
const NODE_WIDTH = 130;
const NODE_HEIGHT = 32;

const RADIAL_SIZE = 600;
const RADIAL_RADIUS = 200;

// --- Helper Hook for Pan and Zoom ---
function usePanZoom(initialScale = 1, minScale = 0.2, maxScale = 4) {
  const [transform, setTransform] = useState({ x: 0, y: 0, k: initialScale });
  const [isDragging, setIsDragging] = useState(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const svgRef = useRef(null);

  const setZoom = useCallback((newK, clientX, clientY) => {
    if (!svgRef.current) return;
    const svgRect = svgRef.current.getBoundingClientRect();
    const cx = clientX !== undefined ? clientX - svgRect.left : svgRect.width / 2;
    const cy = clientY !== undefined ? clientY - svgRect.top : svgRect.height / 2;

    setTransform((prev) => {
      const clampedK = Math.min(Math.max(newK, minScale), maxScale);
      const scaleRatio = clampedK / prev.k;
      return {
        x: cx - (cx - prev.x) * scaleRatio,
        y: cy - (cy - prev.y) * scaleRatio,
        k: clampedK,
      };
    });
  }, [minScale, maxScale]);

  const handleWheel = useCallback((e) => {
    e.preventDefault();
    const scaleFactor = e.deltaY > 0 ? 0.9 : 1.1;
    setZoom(transform.k * scaleFactor, e.clientX, e.clientY);
  }, [transform.k, setZoom]);

  useEffect(() => {
    const el = svgRef.current;
    if (el) {
      el.addEventListener("wheel", handleWheel, { passive: false });
      return () => el.removeEventListener("wheel", handleWheel);
    }
  }, [handleWheel]);

  const handlePointerDown = (e) => {
    if (e.button !== 0) return; 
    setIsDragging(true);
    dragStart.current = { x: e.clientX - transform.x, y: e.clientY - transform.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e) => {
    if (!isDragging) return;
    setTransform((prev) => ({
      ...prev,
      x: e.clientX - dragStart.current.x,
      y: e.clientY - dragStart.current.y,
    }));
  };

  const handlePointerUp = (e) => {
    setIsDragging(false);
    e.currentTarget.releasePointerCapture(e.pointerId);
  };

  const zoomIn = () => setZoom(transform.k * 1.2);
  const zoomOut = () => setZoom(transform.k * 0.8);
  const reset = () => setTransform({ x: 0, y: 0, k: initialScale });

  return {
    svgRef,
    transform,
    isDragging,
    handlers: {
      onPointerDown: handlePointerDown,
      onPointerMove: handlePointerMove,
      onPointerUp: handlePointerUp,
      onPointerCancel: handlePointerUp,
    },
    controls: { zoomIn, zoomOut, reset }
  };
}

// --- Zoom Controls Component ---
function ZoomControls({ onZoomIn, onZoomOut, onReset }) {
  return (
    <div className="sdg-zoom-controls" role="group" aria-label="Zoom controls">
      <button onClick={onZoomIn} aria-label="Zoom in" title="Zoom in">+</button>
      <button onClick={onReset} aria-label="Reset zoom" title="Reset view">⟲</button>
      <button onClick={onZoomOut} aria-label="Zoom out" title="Zoom out">−</button>
    </div>
  );
}

// --- Helper Functions ---
function nodeColor(violationId, violationsById) {
  if (!violationId) return null;
  const violation = violationsById.get(violationId);
  return violation ? getSeverityMeta(violation.severity).color : null;
}

// --- Node Component ---
function GraphNode({ node, color, isInteractive, isTarget, isFlag, onClick }) {
  let classes = "sdg-node-content";
  if (isInteractive) classes += " sdg-node-content--interactive";
  if (isTarget) classes += " sdg-node-content--target";
  if (isFlag) classes += " sdg-node-content--flag";

  const style = {};
  if (color && !isTarget) style.borderColor = color;
  if (color && isInteractive) style.boxShadow = `0 0 0 1px ${color} inset`;

  const handleClick = (e) => {
    if (!isInteractive) return;
    e.stopPropagation();
    onClick();
  };

  const handlePointerDown = (e) => {
    if (!isInteractive) return;
    e.stopPropagation(); 
  };

  const handleKeyDown = (e) => {
    if (!isInteractive) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      e.stopPropagation();
      onClick();
    }
  };

  return (
    <g transform={`translate(${node.px}, ${node.py})`} className="sdg-graph-modal__node">
      <foreignObject
        x={-NODE_WIDTH / 2}
        y={-NODE_HEIGHT / 2}
        width={NODE_WIDTH}
        height={NODE_HEIGHT}
        style={{ overflow: 'visible' }}
      >
        <div
          className={classes}
          style={style}
          title={node.note || node.label}
          role={isInteractive ? "button" : undefined}
          tabIndex={isInteractive ? 0 : undefined}
          onClick={handleClick}
          onPointerDown={handlePointerDown}
          onKeyDown={handleKeyDown}
        >
          <span className="sdg-node-text">{node.label}</span>
        </div>
      </foreignObject>
    </g>
  );
}

// --- Document Tree Graph ---
function DocumentTreeGraph({ documentGraph, violationsById, onSelectViolation }) {
  // SAFETY CHECK: Prevents crashing if data hasn't loaded yet
  if (!documentGraph || !Array.isArray(documentGraph.nodes) || documentGraph.nodes.length === 0) {
    return (
      <div className="sdg-canvas-container">
        <div className="sdg-graph-modal__empty">
          <p>No document structure available yet.</p>
        </div>
      </div>
    );
  }

  const { nodes, edges } = layoutDocumentTree(documentGraph.nodes, documentGraph.rootId);
  const { svgRef, transform, isDragging, handlers, controls } = usePanZoom(1);

  const byId = new Map(nodes.map((n) => {
    return [n.id, { ...n, px: TREE_PADDING + n.x * TREE_X_SPACING, py: TREE_PADDING + n.depth * TREE_Y_SPACING }];
  }));

  return (
    <div className="sdg-canvas-container">
      <svg
        ref={svgRef}
        className={`sdg-graph-modal__svg ${isDragging ? 'dragging' : ''}`}
        {...handlers}
        role="img"
        aria-label="Full document DOM graph. Use mouse wheel to zoom, click and drag to pan."
      >
        <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.k})`}>
          {edges.map((edge, index) => {
            // FIX: Safely support both 'source'/'target' (backend) and 'from'/'to' (fallback)
            const sourceId = edge.source || edge.from;
            const targetId = edge.target || edge.to;
            
            const from = byId.get(sourceId);
            const to = byId.get(targetId);
            
            // SAFETY CHECK: Prevents crashing if the edge points to a missing node
            if (!from || !to) return null;

            return (
              <line
                key={`edge-${sourceId}-${targetId}-${index}`}
                x1={from.px}
                y1={from.py + NODE_HEIGHT / 2}
                x2={to.px}
                y2={to.py - NODE_HEIGHT / 2}
                className="sdg-graph-modal__edge"
              />
            );
          })}
          {Array.from(byId.values()).map((node) => (
            <GraphNode
              key={node.id}
              node={node}
              color={nodeColor(node.violationId, violationsById)}
              isInteractive={Boolean(node.violationId)}
              onClick={() => onSelectViolation(node.violationId)}
            />
          ))}
        </g>
      </svg>
      <ZoomControls onZoomIn={controls.zoomIn} onZoomOut={controls.zoomOut} onReset={controls.reset} />
    </div>
  );
}

// --- Radial Graph ---
function RadialGraph({ context }) {
  // SAFETY CHECK
  if (!context) {
    return (
      <div className="sdg-canvas-container">
        <div className="sdg-graph-modal__empty">
          <p>No local relationship context found.</p>
        </div>
      </div>
    );
  }

  const { nodes, edges } = layoutRadialGraph(context);
  const center = RADIAL_SIZE / 2;
  
  const byId = new Map(nodes.map((n) => {
    return [n.id, { 
      ...n, 
      px: center + n.x * RADIAL_RADIUS, 
      py: center + n.y * RADIAL_RADIUS 
    }];
  }));

  const { svgRef, transform, isDragging, handlers, controls } = usePanZoom(1);

  return (
    <div className="sdg-canvas-container">
      <svg
        ref={svgRef}
        className={`sdg-graph-modal__svg ${isDragging ? 'dragging' : ''}`}
        {...handlers}
        role="img"
        aria-label="Selected violation's SDG relationships. Use mouse wheel to zoom, click and drag to pan."
      >
        <g transform={`translate(${transform.x}, ${transform.y}) scale(${transform.k})`}>
          <g transform={`translate(${svgRef.current ? svgRef.current.clientWidth/2 - center : 0}, ${svgRef.current ? svgRef.current.clientHeight/2 - center : 0})`}>
            {edges.map((edge, index) => {
              // FIX: Safely support both 'source'/'target' and 'from'/'to'
              const sourceId = edge.source || edge.from;
              const targetId = edge.target || edge.to;
              
              const from = byId.get(sourceId);
              const to = byId.get(targetId);
              
              // SAFETY CHECK
              if (!from || !to) return null;

              return (
                <line
                  key={`radial-edge-${sourceId}-${targetId}-${index}`}
                  x1={from.px}
                  y1={from.py}
                  x2={to.px}
                  y2={to.py}
                  className="sdg-graph-modal__edge"
                />
              );
            })}
            {Array.from(byId.values()).map((node) => (
              <GraphNode
                key={node.id}
                node={node}
                isTarget={node.kind === "target"}
                isFlag={node.isFlag}
              />
            ))}
          </g>
        </g>
      </svg>
      <ZoomControls onZoomIn={controls.zoomIn} onZoomOut={controls.zoomOut} onReset={controls.reset} />
    </div>
  );
}

// --- Main Modal Component ---
function SdgGraphModal({ violation, context, documentGraph, violations, onClose, onSelectViolation }) {
  const [view, setView] = useState(violation ? "local" : "document");
  const closeButtonRef = useRef(null);
  const violationsById = new Map((violations || []).map((item) => [item.id, item]));

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

        <div className="sdg-graph-modal__canvas-area">
          {view === "local" ? (
            violation && context ? (
              <RadialGraph context={context} />
            ) : (
              <div className="sdg-graph-modal__empty">
                <p>Select a violation first to see its local relationships.</p>
              </div>
            )
          ) : (
            <DocumentTreeGraph
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
            Outlined nodes have a detected violation — click one to jump to it.
          </footer>
        )}
      </div>
    </div>
  );
}

export default SdgGraphModal;