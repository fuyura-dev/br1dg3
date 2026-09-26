/**
 * Graph Data Parser & Layout Utilities for the Semantic Dependency Graph (SDG).
 *
 * Handles:
 * - Parallel multi-edge consolidation (MultiDiGraph -> combined relation label)
 * - Bidirectional edge curvature so opposite arrows never overlap
 * - Filtering isolated non-SDG DOM nodes in Full Document view
 * - True multi-hop ContextSubgraph rendering in Selected Violation view
 */

function consolidateParallelLinks(rawLinks) {
  const byPair = new Map();

  for (const link of rawLinks || []) {
    const src = String(link.source?.id ?? link.source);
    const tgt = String(link.target?.id ?? link.target);
    if (!src || !tgt) continue;

    const key = `${src}-->${tgt}`;
    if (!byPair.has(key)) {
      byPair.set(key, {
        source: src,
        target: tgt,
        relations: [],
        derived: Boolean(link.derived),
      });
    }
    const entry = byPair.get(key);
    if (link.relation && !entry.relations.includes(link.relation)) {
      entry.relations.push(link.relation);
    }
    entry.derived = entry.derived && Boolean(link.derived);
  }

  const consolidated = [];
  for (const [key, entry] of byPair.entries()) {
    const reverseKey = `${entry.target}-->${entry.source}`;
    const hasReverse = entry.source !== entry.target && byPair.has(reverseKey);
    consolidated.push({
      source: entry.source,
      target: entry.target,
      relation: entry.relations.join(", "),
      derived: entry.derived,
      curvature: hasReverse ? 0.26 : 0,
    });
  }

  return consolidated;
}

export function layoutDocumentTree(documentGraph, { showIsolated = false } = {}) {
  if (!documentGraph || !Array.isArray(documentGraph.nodes)) {
    return { nodes: [], links: [], isolatedCount: 0 };
  }

  const links = consolidateParallelLinks(documentGraph.links || []);
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
    const links = consolidateParallelLinks(context.links || context.edges || []);
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

  return { nodes, links: consolidateParallelLinks(rawLinks) };
}

function formatTag(node) {
  if (!node || !node.tag || typeof node.tag !== "string") return "<unknown>";
  return `<${node.tag.toLowerCase()}>`;
}