import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { layoutDocumentTree, layoutRadialGraph } from "../../utils/graphLayout.js";
import "../../styles/SdgGraphModal.css";

// Canvas 2D requires real hex/rgb colors (CSS custom properties like var(--color-*) are invalid in ctx.fillStyle)
const IMPACT_COLORS = {
  critical: "#ef4444",
  serious: "#f97316",
  moderate: "#eab308",
  minor: "#3b82f6",
};

function getImpactHexColor(impact) {
  return IMPACT_COLORS[impact] || IMPACT_COLORS.moderate;
}

const drawNode = (node, ctx, globalScale) => {
  if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;

  const isTarget = node.kind === "target" || Boolean(node.is_target);
  const hasViolation = isTarget || Boolean(node.violationId) || Boolean(node.has_issue);
  const radius = isTarget ? 8 : hasViolation ? 7 : 5.5;
  const fillColor = node.color || (isTarget ? "#ef4444" : "#38bdf8");

  ctx.save();

  // Outer halo for target or violated nodes
  if (isTarget || hasViolation) {
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius + 3.5, 0, 2 * Math.PI, false);
    ctx.fillStyle = isTarget ? "rgba(239, 68, 68, 0.28)" : "rgba(249, 115, 22, 0.22)";
    ctx.fill();
  }

  // Node circle
  ctx.beginPath();
  ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
  ctx.fillStyle = fillColor;
  ctx.fill();
  ctx.lineWidth = isTarget ? 2 : 1.2;
  ctx.strokeStyle = isTarget ? "#fecaca" : "#0f172a";
  ctx.stroke();

  // Node text label pill below circle
  const prefix = isTarget ? "[T] " : node.violationId ? `[${node.violationId}] ` : "";
  const rawText = `${prefix}${node.name || node.label || `<${node.tag || "node"}>`}`;
  const fontSize = Math.max(3.2, Math.min(11 / Math.sqrt(Math.max(globalScale, 0.6)), 5.5));
  ctx.font = `${isTarget || hasViolation ? "600" : "500"} ${fontSize}px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`;

  const textWidth = ctx.measureText(rawText).width;
  const padX = 3;
  const padY = 1.6;
  const boxW = textWidth + padX * 2;
  const boxH = fontSize + padY * 2;
  const boxX = node.x - boxW / 2;
  const boxY = node.y + radius + 2.5;

  ctx.fillStyle = isTarget
    ? "rgba(127, 29, 29, 0.92)"
    : hasViolation
    ? "rgba(30, 41, 59, 0.92)"
    : "rgba(15, 23, 42, 0.85)";
  ctx.strokeStyle = isTarget
    ? "rgba(248, 113, 113, 0.75)"
    : hasViolation
    ? "rgba(251, 146, 60, 0.65)"
    : "rgba(148, 163, 184, 0.35)";
  ctx.lineWidth = 0.6;

  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(boxX, boxY, boxW, boxH, 2);
  } else {
    ctx.rect(boxX, boxY, boxW, boxH);
  }
  ctx.fill();
  ctx.stroke();

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = isTarget ? "#fecaca" : hasViolation ? "#fde68a" : "#e2e8f0";
  ctx.fillText(rawText, node.x, boxY + boxH / 2);

  ctx.restore();
};

const paintNodePointerArea = (node, color, ctx) => {
  if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI, false);
  ctx.fill();
};

const drawEdgeLabel = (link, ctx) => {
  if (!link.relation) return;
  const start = link.source;
  const end = link.target;

  if (
    typeof start !== "object" ||
    typeof end !== "object" ||
    !Number.isFinite(start.x) ||
    !Number.isFinite(end.x)
  ) {
    return;
  }

  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 1) return;

  // Offset label position slightly when link is curved so bidirectional labels don't collide
  const curvature = link.curvature || 0;
  const normalX = -dy / dist;
  const normalY = dx / dist;
  const curveOffset = curvature * dist * 0.22;

  const textPos = {
    x: start.x + dx / 2 + normalX * curveOffset,
    y: start.y + dy / 2 + normalY * curveOffset,
  };

  let textAngle = Math.atan2(dy, dx);
  if (textAngle > Math.PI / 2) textAngle = -(Math.PI - textAngle);
  if (textAngle < -Math.PI / 2) textAngle = -(-Math.PI - textAngle);

  const fontSize = 3.2;
  ctx.save();
  ctx.font = `500 ${fontSize}px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`;
  const textWidth = ctx.measureText(link.relation).width;
  const bgW = textWidth + 3;
  const bgH = fontSize + 2;

  ctx.translate(textPos.x, textPos.y);
  ctx.rotate(textAngle);

  ctx.fillStyle = "rgba(15, 23, 42, 0.88)";
  ctx.fillRect(-bgW / 2, -bgH / 2, bgW, bgH);

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = link.derived ? "#fcd34d" : "#86efac";
  ctx.fillText(link.relation, 0, 0);
  ctx.restore();
};

function SdgForceCanvas({
  graphData,
  width,
  height,
  graphRef,
  onNodeClick,
  emptyMessage,
}) {
  useEffect(() => {
    const fg = graphRef.current;
    if (!fg || !graphData.nodes.length) return;

    const charge = fg.d3Force("charge");
    if (charge) charge.strength(-340);
    const linkForce = fg.d3Force("link");
    if (linkForce) linkForce.distance(105);

    fg.d3ReheatSimulation();
    const timer = setTimeout(() => {
      fg.zoomToFit(350, 65);
    }, 280);
    return () => clearTimeout(timer);
  }, [graphData, width, height, graphRef]);

  if (!graphData.nodes.length) {
    return (
      <div className="sdg-graph-modal__empty">
        <p>{emptyMessage}</p>
      </div>
    );
  }

  return (
    <ForceGraph2D
      ref={graphRef}
      width={width}
      height={height}
      graphData={graphData}
      nodeLabel={(n) =>
        n.issues?.length
          ? `${n.name} — ${n.issues.map((i) => i.id).join(", ")}`
          : n.name
      }
      nodeCanvasObject={drawNode}
      nodePointerAreaPaint={paintNodePointerArea}
      linkColor={(link) =>
        link.derived ? "rgba(251, 191, 36, 0.65)" : "rgba(148, 163, 184, 0.55)"
      }
      linkWidth={(link) => (link.derived ? 1.4 : 1.6)}
      linkLineDash={(link) => (link.derived ? [4, 3] : null)}
      linkCurvature="curvature"
      backgroundColor="#0f172a"
      linkDirectionalArrowLength={4.5}
      linkDirectionalArrowRelPos={0.88}
      linkCanvasObjectMode={() => "after"}
      linkCanvasObject={drawEdgeLabel}
      onNodeClick={onNodeClick}
      cooldownTicks={120}
    />
  );
}

function SdgGraphModal({
  violation,
  context,
  documentGraph,
  violations,
  onClose,
  onSelectViolation,
}) {
  const [view, setView] = useState(violation ? "local" : "document");
  const [showIsolated, setShowIsolated] = useState(false);
  const closeButtonRef = useRef(null);
  const canvasAreaRef = useRef(null);
  const graphRef = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 960, height: 600 });

  const violationsById = useMemo(
    () => new Map((violations || []).map((v) => [v.id, v])),
    [violations]
  );
  const violationsByNodeId = useMemo(
    () => new Map((violations || []).map((v) => [v.nodeId, v])),
    [violations]
  );

  useEffect(() => {
    closeButtonRef.current?.focus();
    const handleKeyDown = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  useEffect(() => {
    const el = canvasAreaRef.current;
    if (!el) return;

    const updateSize = () => {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        setDimensions({
          width: Math.floor(rect.width),
          height: Math.floor(rect.height),
        });
      }
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const documentLayout = useMemo(() => {
    const { nodes, links, isolatedCount } = layoutDocumentTree(documentGraph, {
      showIsolated,
    });

    return {
      isolatedCount,
      graphData: {
        nodes: nodes.map((n) => {
          const v =
            (n.violationId && violationsById.get(n.violationId)) ||
            violationsByNodeId.get(n.id) ||
            null;
          const primaryImpact =
            v?.impact || v?.severity || n.issues?.[0]?.impact || null;
          return {
            ...n,
            violationId: v?.id || n.violationId || null,
            name: n.label || `<${n.tag}>`,
            color:
              v || n.has_issue
                ? getImpactHexColor(primaryImpact)
                : "#38bdf8",
          };
        }),
        links,
      },
    };
  }, [documentGraph, showIsolated, violationsById, violationsByNodeId]);

  const localGraphData = useMemo(() => {
    const { nodes, links } = layoutRadialGraph(context);
    return {
      nodes: nodes.map((n) => {
        const isTarget = n.kind === "target" || Boolean(n.is_target);
        const v = violationsByNodeId.get(n.id) || null;
        return {
          ...n,
          violationId: isTarget ? violation?.id : v?.id || null,
          name: n.label || `<${n.tag || "node"}>`,
          color: isTarget
            ? "#ef4444"
            : n.has_issue || v
            ? "#f97316"
            : "#38bdf8",
        };
      }),
      links,
    };
  }, [context, violation, violationsByNodeId]);

  const handleZoomIn = useCallback(() => {
    const fg = graphRef.current;
    if (fg) fg.zoom(fg.zoom() * 1.3, 200);
  }, []);

  const handleZoomOut = useCallback(() => {
    const fg = graphRef.current;
    if (fg) fg.zoom(fg.zoom() / 1.3, 200);
  }, []);

  const handleZoomFit = useCallback(() => {
    const fg = graphRef.current;
    if (fg) fg.zoomToFit(300, 65);
  }, []);

  const activeGraphData =
    view === "local" ? localGraphData : documentLayout.graphData;

  return (
    <div className="sdg-graph-modal__backdrop" onClick={onClose}>
      <div
        className="sdg-graph-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Semantic Dependency Graph Visualizer"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sdg-graph-modal__header">
          <div className="sdg-graph-modal__title-group">
            <h2>SDG Graph Visualizer</h2>
            <p>
              {view === "local"
                ? `Extracted SDG Context Subgraph for ${violation?.id ?? ""} (${
                    activeGraphData.nodes.length
                  } nodes, ${activeGraphData.links.length} edges)`
                : `Full Document SDG (${activeGraphData.nodes.length} nodes, ${activeGraphData.links.length} edges)`}
            </p>
          </div>
          <div className="sdg-graph-modal__controls">
            {view === "document" && documentLayout.isolatedCount > 0 && (
              <label className="sdg-graph-modal__toggle">
                <input
                  type="checkbox"
                  checked={showIsolated}
                  onChange={(e) => setShowIsolated(e.target.checked)}
                />
                <span>
                  Show isolated DOM nodes ({documentLayout.isolatedCount})
                </span>
              </label>
            )}
            <div className="sdg-graph-modal__segmented-control" role="tablist">
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
            <button
              type="button"
              className="sdg-graph-modal__close"
              onClick={onClose}
              ref={closeButtonRef}
            >
              Close
            </button>
          </div>
        </header>

        <div className="sdg-graph-modal__canvas-area" ref={canvasAreaRef}>
          {view === "local" && (!violation || !context) ? (
            <div className="sdg-graph-modal__empty">
              <p>Select a violation first to inspect its SDG context subgraph.</p>
            </div>
          ) : (
            <SdgForceCanvas
              graphRef={graphRef}
              graphData={activeGraphData}
              width={dimensions.width}
              height={dimensions.height}
              emptyMessage={
                view === "local"
                  ? "No local SDG context found for this violation."
                  : "No document structure available. Run Scan first."
              }
              onNodeClick={(node) => {
                if (node.violationId && view === "document") {
                  onSelectViolation(node.violationId);
                  setView("local");
                }
              }}
            />
          )}

          <div className="sdg-zoom-controls" aria-label="Graph zoom controls">
            <button type="button" onClick={handleZoomIn} title="Zoom in">
              +
            </button>
            <button type="button" onClick={handleZoomOut} title="Zoom out">
              &minus;
            </button>
            <button type="button" onClick={handleZoomFit} title="Fit graph to view">
              &#x2922;
            </button>
          </div>
        </div>

        <footer className="sdg-graph-modal__footer">
          <span className="sdg-legend-item">
            <span className="sdg-legend-dot sdg-legend-dot--target" />
            Target / Critical Violation
          </span>
          <span className="sdg-legend-item">
            <span className="sdg-legend-dot sdg-legend-dot--violation" />
            Violated Element (click in Full Document view to inspect)
          </span>
          <span className="sdg-legend-item">
            <span className="sdg-legend-dot sdg-legend-dot--context" />
            SDG Structural / Context Node
          </span>
          <span className="sdg-legend-item">
            <span className="sdg-legend-line sdg-legend-line--static" />
            Static SDG Edge
          </span>
          <span className="sdg-legend-item">
            <span className="sdg-legend-line sdg-legend-line--derived" />
            Derived Context Connector
          </span>
        </footer>
      </div>
    </div>
  );
}

export default SdgGraphModal;