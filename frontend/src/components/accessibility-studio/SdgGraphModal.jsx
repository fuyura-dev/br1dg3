import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { forceX, forceY, forceCollide } from "d3-force-3d";
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

const drawEdgeLabel = (link, ctx, globalScale = 1) => {
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

  // Keep font size legible and scale-compensated so it never becomes an invisible hairline
  const fontSize = Math.max(3.8, Math.min(10 / Math.sqrt(Math.max(globalScale, 0.45)), 6.5));
  ctx.save();
  ctx.font = `600 ${fontSize}px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`;
  const textWidth = ctx.measureText(link.relation).width;
  const padX = 3.2;
  const padY = 1.6;
  const bgW = textWidth + padX * 2;
  const bgH = fontSize + padY * 2;

  ctx.translate(textPos.x, textPos.y);
  ctx.rotate(textAngle);

  ctx.fillStyle = "rgba(15, 23, 42, 0.92)";
  ctx.strokeStyle = link.derived ? "rgba(251, 191, 36, 0.75)" : "rgba(134, 239, 172, 0.65)";
  ctx.lineWidth = 0.6;

  ctx.beginPath();
  if (ctx.roundRect) {
    ctx.roundRect(-bgW / 2, -bgH / 2, bgW, bgH, 2);
  } else {
    ctx.rect(-bgW / 2, -bgH / 2, bgW, bgH);
  }
  ctx.fill();
  ctx.stroke();

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = link.derived ? "#fde047" : "#86efac";
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
  isLocalView = false,
}) {
  const [hoveredNode, setHoveredNode] = useState(null);
  const [hoveredLink, setHoveredLink] = useState(null);

  const connectedNodeIds = useMemo(() => {
    if (!hoveredNode) return new Set();
    const ids = new Set([String(hoveredNode.id)]);
    for (const link of graphData.links || []) {
      const srcId = String(link.source?.id ?? link.source);
      const tgtId = String(link.target?.id ?? link.target);
      if (srcId === String(hoveredNode.id)) ids.add(tgtId);
      if (tgtId === String(hoveredNode.id)) ids.add(srcId);
    }
    return ids;
  }, [hoveredNode, graphData.links]);

  useEffect(() => {
    const fg = graphRef.current;
    if (!fg || !graphData.nodes.length) return;

    const chargeStrength = isLocalView ? -320 : -180;
    const chargeDistMax = isLocalView ? 450 : 320;
    const linkDistance = isLocalView ? 120 : 75;
    const gravityStrength = isLocalView ? 0.015 : 0.012;

    const charge = fg.d3Force("charge");
    if (charge) {
      charge.strength(chargeStrength);
      if (typeof charge.distanceMax === "function") {
        charge.distanceMax(chargeDistMax);
      }
    }

    const linkForce = fg.d3Force("link");
    if (linkForce) {
      linkForce.distance(linkDistance);
    }

    fg.d3Force(
      "collide",
      forceCollide(isLocalView ? 24 : 15)
        .strength(0.5)
        .iterations(1)
    );
    fg.d3Force("x", forceX(0).strength(gravityStrength));
    fg.d3Force("y", forceY(0).strength(gravityStrength));

    fg.d3ReheatSimulation();
    const timer = setTimeout(() => {
      if (graphData.nodes.length === 1) {
        const n0 = graphData.nodes[0];
        const nx = Number.isFinite(n0?.x) ? n0.x : 0;
        const ny = Number.isFinite(n0?.y) ? n0.y : 0;
        fg.centerAt(nx, ny, 300);
        fg.zoom(4.0, 300);
      } else if (graphData.nodes.length === 2) {
        fg.zoomToFit(350, 110);
        setTimeout(() => {
          if (fg.zoom() > 2.6) {
            fg.zoom(2.4, 150);
          }
        }, 360);
      } else {
        fg.zoomToFit(350, isLocalView ? 75 : 50);
        setTimeout(() => {
          if (fg.zoom() > 1.8) {
            fg.zoom(1.6, 150);
          }
        }, 360);
      }
    }, 280);
    return () => clearTimeout(timer);
  }, [graphData, width, height, graphRef, isLocalView]);

  const drawCustomNode = useCallback(
    (node, ctx, globalScale) => {
      if (!Number.isFinite(node.x) || !Number.isFinite(node.y)) return;

      const isHovered = hoveredNode && (String(node.id) === String(hoveredNode.id) || connectedNodeIds.has(String(node.id)));
      const isDimmed = hoveredNode && !isHovered;

      ctx.save();
      if (isDimmed) {
        ctx.globalAlpha = 0.22;
      }

      const isTarget = node.kind === "target" || Boolean(node.is_target);
      const hasViolation = isTarget || Boolean(node.violationId) || Boolean(node.has_issue);
      const radius = isTarget ? 8.5 : hasViolation ? 7.5 : 5.5;
      const fillColor = node.color || (isTarget ? "#ef4444" : "#38bdf8");

      // Outer halo for target or violated nodes or hovered node
      if (isTarget || hasViolation || (hoveredNode && String(node.id) === String(hoveredNode.id))) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + 4, 0, 2 * Math.PI, false);
        ctx.fillStyle = isTarget
          ? "rgba(239, 68, 68, 0.32)"
          : (hoveredNode && String(node.id) === String(hoveredNode.id))
          ? "rgba(56, 189, 248, 0.35)"
          : "rgba(249, 115, 22, 0.24)";
        ctx.fill();
      }

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = fillColor;
      ctx.fill();
      ctx.lineWidth = isTarget || (hoveredNode && String(node.id) === String(hoveredNode.id)) ? 2.2 : 1.2;
      ctx.strokeStyle = isTarget ? "#fecaca" : "#0f172a";
      ctx.stroke();

      // Node text label pill below circle (compact, max 24 chars so it never forms a giant brick)
      const prefix = isTarget ? "[T] " : node.violationId ? `[${node.violationId}] ` : "";
      let rawText = `${prefix}${node.name || node.label || `<${node.tag || "node"}>`}`;
      if (rawText.length > 24) {
        rawText = rawText.slice(0, 22) + "…";
      }

      const fontSize = Math.max(3.2, Math.min(10 / Math.sqrt(Math.max(globalScale, 0.6)), 5.2));
      ctx.font = `${isTarget || hasViolation ? "600" : "500"} ${fontSize}px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`;

      const textWidth = ctx.measureText(rawText).width;
      const padX = 3;
      const padY = 1.5;
      const boxW = textWidth + padX * 2;
      const boxH = fontSize + padY * 2;
      const boxX = node.x - boxW / 2;
      const boxY = node.y + radius + 2.5;

      ctx.fillStyle = isTarget
        ? "rgba(127, 29, 29, 0.92)"
        : hasViolation
        ? "rgba(30, 41, 59, 0.92)"
        : "rgba(15, 23, 42, 0.88)";
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
    },
    [hoveredNode, connectedNodeIds]
  );

  const drawCustomEdgeLabel = useCallback(
    (link, ctx, globalScale = 1) => {
      if (!link.relation) return;

      // In Full Document view, don't draw 60 overlapping text boxes unless hovered or zoomed in!
      if (!isLocalView) {
        const isLinkHovered = hoveredLink === link;
        const isSrcOrTgtHovered =
          hoveredNode &&
          (String(link.source?.id ?? link.source) === String(hoveredNode.id) ||
            String(link.target?.id ?? link.target) === String(hoveredNode.id));
        const isZoomedIn = globalScale >= 0.92;
        if (!isLinkHovered && !isSrcOrTgtHovered && !isZoomedIn) {
          return;
        }
      }

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

      const fontSize = Math.max(3.6, Math.min(9.5 / Math.sqrt(Math.max(globalScale, 0.45)), 5.8));
      ctx.save();
      ctx.font = `600 ${fontSize}px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`;
      const textWidth = ctx.measureText(link.relation).width;
      const padX = 3.0;
      const padY = 1.4;
      const bgW = textWidth + padX * 2;
      const bgH = fontSize + padY * 2;

      ctx.translate(textPos.x, textPos.y);
      ctx.rotate(textAngle);

      ctx.fillStyle = "rgba(15, 23, 42, 0.94)";
      ctx.strokeStyle = link.derived ? "rgba(251, 191, 36, 0.8)" : "rgba(134, 239, 172, 0.7)";
      ctx.lineWidth = 0.6;

      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(-bgW / 2, -bgH / 2, bgW, bgH, 2);
      } else {
        ctx.rect(-bgW / 2, -bgH / 2, bgW, bgH);
      }
      ctx.fill();
      ctx.stroke();

      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = link.derived ? "#fde047" : "#86efac";
      ctx.fillText(link.relation, 0, 0);
      ctx.restore();
    },
    [isLocalView, hoveredNode, hoveredLink]
  );

  const getCustomLinkColor = useCallback(
    (link) => {
      if (hoveredLink === link) {
        return link.derived ? "#fde047" : "#86efac";
      }
      if (hoveredNode) {
        const srcId = String(link.source?.id ?? link.source);
        const tgtId = String(link.target?.id ?? link.target);
        if (srcId === String(hoveredNode.id) || tgtId === String(hoveredNode.id)) {
          return link.derived ? "#fde047" : "#86efac";
        }
        return "rgba(148, 163, 184, 0.10)";
      }
      return link.derived ? "rgba(251, 191, 36, 0.65)" : "rgba(148, 163, 184, 0.55)";
    },
    [hoveredNode, hoveredLink]
  );

  const getCustomLinkWidth = useCallback(
    (link) => {
      if (hoveredLink === link) {
        return 2.5;
      }
      if (hoveredNode) {
        const srcId = String(link.source?.id ?? link.source);
        const tgtId = String(link.target?.id ?? link.target);
        if (srcId === String(hoveredNode.id) || tgtId === String(hoveredNode.id)) {
          return 2.2;
        }
        return 0.8;
      }
      return link.derived ? 1.4 : 1.6;
    },
    [hoveredNode, hoveredLink]
  );

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
      nodeCanvasObject={drawCustomNode}
      nodePointerAreaPaint={paintNodePointerArea}
      linkColor={getCustomLinkColor}
      linkWidth={getCustomLinkWidth}
      linkLineDash={(link) => (link.derived ? [4, 3] : null)}
      linkCurvature="curvature"
      backgroundColor="#0f172a"
      linkDirectionalArrowLength={4.5}
      linkDirectionalArrowRelPos={0.88}
      linkCanvasObjectMode={() => "after"}
      linkCanvasObject={drawCustomEdgeLabel}
      onNodeClick={onNodeClick}
      onNodeHover={(node) => setHoveredNode(node || null)}
      onLinkHover={(link) => setHoveredLink(link || null)}
      d3VelocityDecay={0.45}
      d3AlphaDecay={0.03}
      cooldownTicks={100}
      cooldownTime={2000}
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

  const activeGraphData =
    view === "local" ? localGraphData : documentLayout.graphData;

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
    if (!fg) return;
    if (activeGraphData.nodes.length === 1) {
      const n0 = activeGraphData.nodes[0];
      fg.centerAt(n0?.x ?? 0, n0?.y ?? 0, 300);
      fg.zoom(4.0, 300);
    } else if (activeGraphData.nodes.length === 2) {
      fg.zoomToFit(300, 110);
      setTimeout(() => {
        if (fg.zoom() > 2.6) fg.zoom(2.4, 150);
      }, 310);
    } else {
      fg.zoomToFit(300, view === "local" ? 75 : 50);
      setTimeout(() => {
        if (fg.zoom() > 1.8) fg.zoom(1.6, 150);
      }, 310);
    }
  }, [activeGraphData, view]);

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
              isLocalView={view === "local"}
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