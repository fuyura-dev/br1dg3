/**
 * Graph Data Parser Utilities
 * 
 * Since we migrated to react-force-graph-2d, manual X/Y coordinate math is obsolete.
 * The library's physics engine automatically handles Directed Graphs, cycles, and multi-parent structures.
 * These functions now simply parse the raw backend data into flat { nodes, edges } arrays.
 */

/**
 * Full-Document View Parser
 * 
 * Extracts nodes and generates edges from a Directed Graph.
 * Safely handles multi-parent arrays and cycles without recursive infinite loops.
 * 
 * @param {Array} nodes - Array of node objects.
 * @param {String} rootId - The ID of the root node (kept for backwards compatibility).
 * @returns {Object} { nodes, edges } for ForceGraph2D.
 */
export function layoutDocumentTree(nodes, rootId) {
  if (!nodes || !Array.isArray(nodes)) {
    return { nodes: [], edges: [] };
  }

  const flatNodes = [];
  const edges = [];

  nodes.forEach((node) => {
    // Ipasa ang node as is, wala nang manual x/y
    flatNodes.push({ ...node });

    // SUPPORT FOR DIRECTED GRAPH:
    // Kayang basahin ang new format na 'parents: []' o ang lumang 'parent: ""'
    const parents = Array.isArray(node.parents) 
      ? node.parents 
      : (node.parent ? [node.parent] : []);
    
    parents.forEach((parentId) => {
      edges.push({ 
        source: parentId, 
        target: node.id, 
        relation: 'dependency' 
      });
    });

    // FALLBACK: Kung ang backend niyo ay nagpapadala rin ng 'dependencies' array pababa
    if (Array.isArray(node.dependencies)) {
      node.dependencies.forEach((depId) => {
        edges.push({ 
          source: node.id, 
          target: depId, 
          relation: 'dependency' 
        });
      });
    }
  });

  return { nodes: flatNodes, edges };
}

/**
 * Local View (Radial) Parser
 * 
 * Maps related nodes to the central target. The react-force-graph-2d 
 * 'radialout' dagMode will handle the circular visual layout automatically.
 * 
 * @param {Object} context - An object containing arrays of related elements.
 * @returns {Object} { nodes, edges } for ForceGraph2D.
 */
export function layoutRadialGraph(context) {
  if (!context || !context.target) {
    return { nodes: [], edges: [] };
  }

  const satellites = [];
  const edges = [];
  
  const pushGroup = (items, kind) => {
    (items ?? []).forEach((item, index) => {
      const satId = `${kind}-${index}`;
      satellites.push({
        id: satId,
        label: item.tag ? formatTag(item) : (item.status || "Unknown"),
        note: item.note,
        kind,
        isFlag: !item.tag,
      });

      // Gawa agad ng edge, wala nang trigonometry (Math.cos / Math.sin)
      edges.push({ 
        source: "target", 
        target: satId,
        relation: kind
      });
    });
  };

  // Support for multiple parents sa context panel
  if (context.parent) {
    const parents = Array.isArray(context.parent) ? context.parent : [context.parent];
    pushGroup(parents, "parent");
  }
  
  pushGroup(context.children, "child");
  pushGroup(context.siblings, "sibling");
  pushGroup(context.labelRelationships, "label");
  pushGroup(context.headingRelationships, "heading");
  pushGroup(context.formRelationships, "form");

  const center = { 
    id: "target", 
    label: formatTag(context.target), 
    kind: "target" 
  };

  return { nodes: [center, ...satellites], edges };
}

/**
 * Formats the display label for an HTML element node.
 * 
 * @param {Object} node - The node object containing a 'tag' string.
 * @returns {String} The formatted tag label.
 */
function formatTag(node) {
  if (!node || !node.tag || typeof node.tag !== 'string') {
    return "<unknown>";
  }
  return `<${node.tag.toLowerCase()}>`;
}