import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import cytoscape from "cytoscape";
import { layoutDocumentTree, layoutRadialGraph } from "../../utils/graphLayout.js";
import "../../styles/SdgGraphModal.css";

const IMPACT_COLORS = {
  critical: "#ef4444",
  serious: "#f97316",
  moderate: "#eab308",
  minor: "#3b82f6",
};

function getImpactHexColor(impact) {
  return IMPACT_COLORS[impact] || IMPACT_COLORS.moderate;
}

export const RELATION_CONFIG = {
  focus_order: {
    color: "#06b6d4",
    label: "Focus Order",
  },
  parent_child: {
    color: "#64748b",
    label: "Parent-Child",
  },
  heading_hierarchy: {
    color: "#818cf8",
    label: "Heading Hierarchy",
  },
  label_input: {
    color: "#10b981",
    label: "Label Input",
  },
  aria_labelledby: {
    color: "#a855f7",
    label: "ARIA Labelledby",
  },
  aria_describedby: {
    color: "#c084fc",
    label: "ARIA Describedby",
  },
  aria_controls: {
    color: "#e879f9",
    label: "ARIA Controls",
  },
  landmark_structure: {
    color: "#f59e0b",
    label: "Landmark Structure",
  },
  form_group: {
    color: "#f97316",
    label: "Form Group",
  },
  name_group: {
    color: "#fb923c",
    label: "Name Group",
  },
  id_reference: {
    color: "#f43f5e",
    label: "ID Reference",
  },
};

export function getRelationColor(relation) {
  return RELATION_CONFIG[relation]?.color || "#94a3b8";
}

export function getRelationLabel(relation) {
  return RELATION_CONFIG[relation]?.label || relation.replace(/_/g, " ");
}

function SdgCytoscapeCanvas({
  graphData,
  graphRef,
  onNodeClick,
  emptyMessage,
  isLocalView = false,
}) {
  const containerRef = useRef(null);
  const cyInstanceRef = useRef(null);
  const onNodeClickRef = useRef(onNodeClick);

  useEffect(() => {
    onNodeClickRef.current = onNodeClick;
  }, [onNodeClick]);

  // Initialize Cytoscape once container mounts
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      boxSelectionEnabled: false,
      autounselectify: true,
      wheelSensitivity: 1.0,
      minZoom: 0.12,
      maxZoom: 4.5,
      style: [
        {
          selector: "node",
          style: {
            shape: "round-rectangle",
            "background-color": "data(bgColor)",
            "border-width": 2,
            "border-color": "data(borderColor)",
            label: "data(label)",
            color: "#ffffff",
            "font-size": "11px",
            "font-weight": "600",
            "font-family": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            "text-valign": "center",
            "text-halign": "center",
            "text-wrap": "wrap",
            "text-max-width": "240px",
            padding: "8px 12px",
            width: "label",
            height: "label",
            "min-width": "46px",
            "min-height": "28px",
            "transition-property": "background-color, border-color, border-width, opacity",
            "transition-duration": "0.15s",
          },
        },
        {
          selector: "node[?isTarget]",
          style: {
            "background-color": "#ef4444",
            "border-color": "#fecaca",
            "border-width": 3,
            "font-size": "12px",
            "font-weight": "700",
            "shadow-blur": 16,
            "shadow-color": "rgba(239, 68, 68, 0.7)",
            "shadow-opacity": 0.8,
            "z-index": 999,
          },
        },
        {
          selector: "node[?hasViolation]",
          style: {
            "border-color": "#f97316",
            "border-width": 2.5,
            "shadow-blur": 10,
            "shadow-color": "rgba(249, 115, 22, 0.5)",
            "shadow-opacity": 0.6,
          },
        },
        {
          selector: "edge",
          style: {
            "curve-style": "bezier",
            "control-point-step-size": 36,
            width: 2.0,
            "line-color": "data(color)",
            "target-arrow-color": "data(color)",
            "target-arrow-shape": "triangle",
            "arrow-scale": 1.1,
            label: "data(relation)",
            "font-size": "9.5px",
            "font-weight": "600",
            "font-family": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            color: "data(color)",
            "text-rotation": "autorotate",
            "text-margin-y": -7,
            "text-background-color": "#0f172a",
            "text-background-opacity": 0.94,
            "text-background-padding": "3px",
            "text-background-shape": "roundrectangle",
            "min-zoomed-font-size": isLocalView ? 0 : 8,
            "transition-property": "line-color, target-arrow-color, width, opacity",
            "transition-duration": "0.15s",
          },
        },
        {
          selector: "edge[?derived]",
          style: {
            "line-style": "dashed",
            "line-dash-pattern": [6, 3],
          },
        },
        // Dynamic interaction states
        {
          selector: "node.hovered",
          style: {
            "border-color": "#38bdf8",
            "border-width": 3,
            "shadow-blur": 18,
            "shadow-color": "rgba(56, 189, 248, 0.8)",
            "shadow-opacity": 0.9,
            "z-index": 1000,
          },
        },
        {
          selector: "node.highlighted",
          style: {
            opacity: 1,
            "border-color": "#38bdf8",
            "z-index": 900,
          },
        },
        {
          selector: "node.dimmed",
          style: {
            opacity: 0.14,
          },
        },
        {
          selector: "edge.hovered",
          style: {
            width: 3.4,
            "font-size": "10.5px",
            "font-weight": "700",
            "min-zoomed-font-size": 0,
            "z-index": 998,
          },
        },
        {
          selector: "edge.highlighted",
          style: {
            opacity: 1,
            width: 2.6,
            "min-zoomed-font-size": 0,
          },
        },
        {
          selector: "edge.dimmed",
          style: {
            opacity: 0.08,
          },
        },
      ],
    });

    cyInstanceRef.current = cy;
    if (graphRef) {
      graphRef.current = cy;
    }

    // Interactive hover highlighting
    cy.on("mouseover", "node", (e) => {
      const node = e.target;
      node.addClass("hovered");
      const neighborhood = node.neighborhood();
      neighborhood.addClass("highlighted");
      cy.elements().not(node).not(neighborhood).addClass("dimmed");
    });

    cy.on("mouseout", "node", () => {
      cy.elements().removeClass("hovered highlighted dimmed");
    });

    cy.on("mouseover", "edge", (e) => {
      const edge = e.target;
      edge.addClass("hovered");
      const connectedNodes = edge.connectedNodes();
      connectedNodes.addClass("highlighted");
      cy.elements().not(edge).not(connectedNodes).addClass("dimmed");
    });

    cy.on("mouseout", "edge", () => {
      cy.elements().removeClass("hovered highlighted dimmed");
    });

    cy.on("tap", "node", (e) => {
      if (onNodeClickRef.current) {
        onNodeClickRef.current(e.target.data());
      }
    });

    cy.on("tap", (e) => {
      if (e.target === cy) {
        cy.elements().removeClass("hovered highlighted dimmed");
      }
    });

    const resizeObserver = new ResizeObserver(() => {
      if (cyInstanceRef.current) {
        cyInstanceRef.current.resize();
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      cy.destroy();
      cyInstanceRef.current = null;
      if (graphRef) {
        graphRef.current = null;
      }
    };
  }, []);

  // Update elements and rerun layout when graphData or view mode changes
  useEffect(() => {
    const cy = cyInstanceRef.current;
    if (!cy) return;

    cy.style()
      .selector("edge")
      .style({
        "min-zoomed-font-size": isLocalView ? 0 : 8,
      })
      .update();

    cy.elements().remove();

    if (!graphData.nodes || graphData.nodes.length === 0) return;

    const elements = [];
    for (const node of graphData.nodes) {
      const isTarget = node.kind === "target" || Boolean(node.is_target);
      const hasViolation = isTarget || Boolean(node.violationId) || Boolean(node.has_issue);
      const prefix = isTarget ? "[T] " : node.violationId ? `[${node.violationId}] ` : "";
      const label = `${prefix}${node.name || node.label || `<${node.tag || "node"}>`}`;

      elements.push({
        group: "nodes",
        data: {
          id: String(node.id),
          label,
          tag: node.tag,
          isTarget,
          hasViolation,
          violationId: node.violationId || null,
          bgColor: node.color || (isTarget ? "#ef4444" : "#38bdf8"),
          borderColor: isTarget
            ? "#fecaca"
            : hasViolation
            ? "#fed7aa"
            : "#93c5fd",
          rawNode: node,
        },
      });
    }

    const nodeIds = new Set(graphData.nodes.map((n) => String(n.id)));
    (graphData.links || []).forEach((link, idx) => {
      const srcId = String(link.source?.id ?? link.source);
      const tgtId = String(link.target?.id ?? link.target);
      if (!nodeIds.has(srcId) || !nodeIds.has(tgtId)) return;

      const rel = link.relation || "";
      elements.push({
        group: "edges",
        data: {
          id: link.id || `e-${srcId}-${tgtId}-${idx}`,
          source: srcId,
          target: tgtId,
          relation: rel,
          color: getRelationColor(rel),
          derived: Boolean(link.derived),
        },
      });
    });

    cy.add(elements);

    // Layout configuration
    if (graphData.nodes.length === 1) {
      const n = cy.nodes()[0];
      if (n) {
        n.position({ x: cy.width() / 2, y: cy.height() / 2 });
      }
      cy.center();
      cy.zoom(2.0);
    } else if (isLocalView) {
      const layout = cy.layout({
        name: "concentric",
        concentric: (node) => (node.data("isTarget") ? 2 : 1),
        levelWidth: () => 1,
        minNodeSpacing: 80,
        padding: 60,
        animate: false,
      });
      layout.run();
      cy.fit(60);
      if (cy.zoom() > 2.0) {
        cy.zoom(1.8);
        cy.center();
      }
    } else {
      const connectedElements = cy.elements().filter((ele) => ele.isEdge() || ele.degree() > 0);
      const isolatedNodes = cy.nodes().filter((node) => node.degree() === 0);

      if (connectedElements.length > 0) {
        // Run cose ONLY on the connected subgraph so physics remains fast and clean
        const layout = connectedElements.layout({
          name: "cose",
          animate: false,
          randomize: false,
          componentSpacing: 120,
          nodeRepulsion: () => 32000,
          nodeOverlap: 8,
          idealEdgeLength: (edge) =>
            edge.data("relation") === "focus_order" ? 170 : 120,
          edgeElasticity: (edge) =>
            edge.data("relation") === "focus_order" ? 35 : 100,
          nestingFactor: 1.2,
          gravity: 0.65,
          numIter: 1000,
          initialTemp: 250,
          coolingFactor: 0.95,
          minTemp: 1.0,
          padding: 60,
        });
        layout.run();

        // Arrange isolated elements in a neat, non-overlapping grid shelf below the main graph
        if (isolatedNodes.length > 0) {
          const bb = connectedElements.boundingBox();
          const colSpacing = 280;
          const rowSpacing = 60;
          const cols = Math.max(1, Math.min(5, Math.ceil(Math.sqrt(isolatedNodes.length))));
          const totalWidth = (cols - 1) * colSpacing;
          const startX = (bb.x1 + bb.x2) / 2 - totalWidth / 2;
          const startY = bb.y2 + 140;

          isolatedNodes.forEach((node, i) => {
            const col = i % cols;
            const row = Math.floor(i / cols);
            node.position({
              x: startX + col * colSpacing,
              y: startY + row * rowSpacing,
            });
          });
        }
      } else {
        // All nodes are isolated: arrange in a clean grid centered at canvas
        const colSpacing = 280;
        const rowSpacing = 60;
        const cols = Math.max(1, Math.min(5, Math.ceil(Math.sqrt(isolatedNodes.length))));
        const totalWidth = (cols - 1) * colSpacing;
        const totalHeight = (Math.ceil(isolatedNodes.length / cols) - 1) * rowSpacing;
        const startX = -totalWidth / 2;
        const startY = -totalHeight / 2;

        isolatedNodes.forEach((node, i) => {
          const col = i % cols;
          const row = Math.floor(i / cols);
          node.position({
            x: startX + col * colSpacing,
            y: startY + row * rowSpacing,
          });
        });
      }

      cy.fit(50);
      if (cy.zoom() > 1.8) {
        cy.zoom(1.4);
        cy.center();
      }
    }
  }, [graphData, isLocalView]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div
        ref={containerRef}
        className="sdg-cytoscape-container"
      />
      {(!graphData.nodes || !graphData.nodes.length) && (
        <div
          className="sdg-graph-modal__empty"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <p>{emptyMessage}</p>
        </div>
      )}
    </div>
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
  const [excludedRelations, setExcludedRelations] = useState(new Set());
  const closeButtonRef = useRef(null);
  const graphRef = useRef(null);

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

  const rawGraphData =
    view === "local" ? localGraphData : documentLayout.graphData;

  // Available relationship types and their edge counts in the current view
  const availableRelations = useMemo(() => {
    const counts = new Map();
    for (const link of rawGraphData.links || []) {
      const rel = link.relation || "other";
      counts.set(rel, (counts.get(rel) || 0) + 1);
    }
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([rel, count]) => ({
        relation: rel,
        count,
        color: getRelationColor(rel),
        label: getRelationLabel(rel),
      }));
  }, [rawGraphData.links]);

  const toggleRelationFilter = useCallback((relation) => {
    setExcludedRelations((prev) => {
      const next = new Set(prev);
      if (next.has(relation)) {
        next.delete(relation);
      } else {
        next.add(relation);
      }
      return next;
    });
  }, []);

  // Filter links according to active user filter chips
  const activeGraphData = useMemo(() => {
    if (excludedRelations.size === 0) return rawGraphData;
    return {
      nodes: rawGraphData.nodes,
      links: (rawGraphData.links || []).filter(
        (link) => !excludedRelations.has(link.relation)
      ),
    };
  }, [rawGraphData, excludedRelations]);

  const handleZoomIn = useCallback(() => {
    const cy = graphRef.current;
    if (cy) {
      cy.zoom({
        level: cy.zoom() * 1.3,
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
      });
    }
  }, []);

  const handleZoomOut = useCallback(() => {
    const cy = graphRef.current;
    if (cy) {
      cy.zoom({
        level: cy.zoom() / 1.3,
        renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
      });
    }
  }, []);

  const handleZoomFit = useCallback(() => {
    const cy = graphRef.current;
    if (!cy) return;
    if (cy.nodes().length === 0) return;
    if (cy.nodes().length === 1) {
      cy.center();
      cy.zoom(2.0);
    } else {
      cy.fit(view === "local" ? 60 : 40);
      if (cy.zoom() > 2.0) {
        cy.zoom(1.8);
        cy.center();
      }
    }
  }, [view]);

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

        {availableRelations.length > 0 && (
          <div className="sdg-filter-bar">
            <span className="sdg-filter-bar__title">Relationships:</span>
            <div className="sdg-filter-chips">
              {availableRelations.map(({ relation, count, color, label }) => {
                const isExcluded = excludedRelations.has(relation);
                return (
                  <button
                    key={relation}
                    type="button"
                    className={`sdg-filter-chip ${
                      isExcluded ? "sdg-filter-chip--inactive" : "sdg-filter-chip--active"
                    }`}
                    onClick={() => toggleRelationFilter(relation)}
                    title={isExcluded ? `Click to show ${label}` : `Click to hide ${label}`}
                  >
                    <span
                      className="sdg-filter-chip__dot"
                      style={{ backgroundColor: color }}
                    />
                    <span className="sdg-filter-chip__label">{label}</span>
                    <span className="sdg-filter-chip__count">{count}</span>
                  </button>
                );
              })}
              {excludedRelations.size > 0 && (
                <button
                  type="button"
                  className="sdg-filter-chip sdg-filter-chip--reset"
                  onClick={() => setExcludedRelations(new Set())}
                >
                  Reset ({excludedRelations.size} hidden)
                </button>
              )}
            </div>
          </div>
        )}

        <div className="sdg-graph-modal__canvas-area">
          {view === "local" && (!violation || !context) ? (
            <div className="sdg-graph-modal__empty">
              <p>Select a violation first to inspect its SDG context subgraph.</p>
            </div>
          ) : (
            <SdgCytoscapeCanvas
              graphRef={graphRef}
              graphData={activeGraphData}
              isLocalView={view === "local"}
              emptyMessage={
                view === "local"
                  ? "No local SDG context found for this violation."
                  : "No document structure available. Run Scan first."
              }
              onNodeClick={(nodeData) => {
                if (nodeData.violationId && view === "document") {
                  onSelectViolation(nodeData.violationId);
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
            Violated Element (click to inspect)
          </span>
          <span className="sdg-legend-item">
            <span className="sdg-legend-dot sdg-legend-dot--context" />
            SDG Structural Node
          </span>
          <span className="sdg-legend-divider" />
          <span className="sdg-legend-tip">
            Tip: Click relationship chips above to hide or isolate edge layers
          </span>
        </footer>
      </div>
    </div>
  );
}

export default SdgGraphModal;