/**
 * Graph Data Parser & Layout Utilities for the Semantic Dependency Graph (SDG).
 *
 * Handles:
 * - MultiDiGraph edge preservation (each relation has its own edge with unique id)
 * - Deduplicating identical duplicate edges while preserving multi-relational edges
 * - Filtering isolated non-SDG DOM nodes in Full Document view
 * - True multi-hop ContextSubgraph rendering in Selected Violation view
 */

export function processMultigraphLinks(rawLinks) {
  const seen = new Set();
  const edges = [];

  for (const link of rawLinks || []) {
    const src = String(link.source?.id ?? link.source);
    const tgt = String(link.target?.id ?? link.target);
    if (!src || !tgt) continue;

    const rel = link.relation || "";
    const isDerived = Boolean(link.derived);
    const key = `${src}-->${tgt}::${rel}::${isDerived}`;
    if (seen.has(key)) continue;
    seen.add(key);

    edges.push({
      id: link.id || `e-${src}-${tgt}-${rel.replace(/[^a-zA-Z0-9_-]/g, "_")}-${edges.length}`,
      source: src,
      target: tgt,
      relation: rel,
      derived: isDerived,
    });
  }

  return edges;
}

export const consolidateParallelLinks = processMultigraphLinks;

export function layoutDocumentTree(documentGraph, { showIsolated = false } = {}) {
  if (!documentGraph || !Array.isArray(documentGraph.nodes)) {
    return { nodes: [], links: [], isolatedCount: 0 };
  }

  const links = processMultigraphLinks(documentGraph.links || []);
  const connectedIds = new Set();
  for (const link of links) {
    connectedIds.add(String(link.source));
    connectedIds.add(String(link.target));
  }

  const allNodes = documentGraph.nodes.map((n) => ({
    ...n,
    id: String(n.id),
    label: n.label || `<${n.tag || "unknown"}>`,
  }));

  const relevantNodes = allNodes.filter(
    (n) => connectedIds.has(n.id) || Boolean(n.has_issue) || Boolean(n.violationId)
  );
  const isolatedCount = Math.max(0, allNodes.length - relevantNodes.length);

  const activeNodes = showIsolated || relevantNodes.length === 0 ? allNodes : relevantNodes;
  const activeIds = new Set(activeNodes.map((n) => n.id));

  return {
    nodes: activeNodes,
    links: links.filter((l) => activeIds.has(l.source) && activeIds.has(l.target)),
    isolatedCount,
  };
}

export function layoutRadialGraph(context) {
  if (!context) {
    return { nodes: [], links: [] };
  }

  // Preferred path: render the exact multi-hop ContextSubgraph extracted by backend ContextExtractor
  if (Array.isArray(context.nodes) && context.nodes.length > 0) {
    const links = processMultigraphLinks(context.links || context.edges || []);
    const nodes = context.nodes.map((n) => {
      const isTarget = Boolean(n.is_target) || n.id === context.targetId;
      return {
        ...n,
        id: String(n.id),
        label: n.label || formatTag(n),
        kind: isTarget ? "target" : n.has_issue ? "violation" : "context",
      };
    });
    return { nodes, links };
  }

  // Fallback path if only legacy grouped relationships are present
  if (!context.target) {
    return { nodes: [], links: [] };
  }

  const nodes = [];
  const rawLinks = [];

  const pushGroup = (items, relation) => {
    const list = Array.isArray(items) ? items : items ? [items] : [];
    list.forEach((item, index) => {
      const satId = `${relation}-${index}`;
      nodes.push({
        id: satId,
        tag: item.tag || null,
        label: item.label || (item.tag ? formatTag(item) : item.status || "Unknown"),
        note: item.note,
        kind: relation,
        isFlag: !item.tag,
      });

      rawLinks.push({
        source: "target",
        target: satId,
        relation: item.relation || relation,
        derived: Boolean(item.derived),
      });
    });
  };

  nodes.push({
    id: "target",
    tag: context.target.tag,
    label: context.target.label || formatTag(context.target),
    kind: "target",
  });

  pushGroup(context.parent, "parent");
  pushGroup(context.children, "child");
  pushGroup(context.siblings, "sibling");
  pushGroup(context.labelRelationships, "label");
  pushGroup(context.headingRelationships, "heading");
  pushGroup(context.formRelationships, "form");

  return { nodes, links: processMultigraphLinks(rawLinks) };
}

function formatTag(node) {
  if (!node || !node.tag || typeof node.tag !== "string") return "<unknown>";
  return `<${node.tag.toLowerCase()}>`;
}