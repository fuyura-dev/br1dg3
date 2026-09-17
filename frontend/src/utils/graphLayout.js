/**
 * Graph Layout Utilities
 * 
 * Pure layout math for the SDG (Semantic Dependency Graph) visualizer. 
 * Both functions process raw data and return plain { nodes, edges } objects 
 * with x/y coordinates assigned, ensuring the UI component only handles rendering.
 * 
 * Note: Edge definitions strictly use 'source' and 'target' properties to 
 * align with the backend's graph schema.
 */

/**
 * Full-Document View Layout
 * 
 * Arranges a flat list of nodes (which contain parent pointers) into a top-down tree.
 * Leaves are assigned sequential X coordinates, and parent nodes are centered 
 * horizontally above their children.
 * 
 * @param {Array} nodes - Array of node objects (must contain `id` and `parent` properties).
 * @param {String} rootId - The ID of the root node to start the tree traversal.
 * @returns {Object} { nodes, edges } with assigned coordinates.
 */
export function layoutDocumentTree(nodes, rootId) {
  // SAFETY CHECK: Ensure nodes is a valid array to prevent app crashes
  if (!nodes || !Array.isArray(nodes)) {
    return { nodes: [], edges: [] };
  }

  // Initialize nodes with an empty children array to prepare for tree construction
  const byId = new Map(nodes.map((node) => [node.id, { ...node, children: [] }]));
  
  // Link children to their respective parent nodes
  byId.forEach((node) => {
    if (node.parent && byId.has(node.parent)) {
      byId.get(node.parent).children.push(node);
    }
  });
  
  const root = byId.get(rootId);
  if (!root) return { nodes: [], edges: [] };

  // Recursive function to calculate and assign the vertical depth (Y-axis)
  const assignDepth = (node, depth) => {
    node.depth = depth;
    node.children.forEach((child) => assignDepth(child, depth + 1));
  };
  assignDepth(root, 0);

  // Recursive function to calculate and assign horizontal positions (X-axis)
  let nextLeafSlot = 0;
  const assignX = (node) => {
    // If it's a leaf node, assign it the next available slot and increment
    if (node.children.length === 0) {
      node.x = nextLeafSlot;
      nextLeafSlot += 1;
      return node.x;
    }
    // If it has children, calculate their positions first, then center the parent over them
    const childXs = node.children.map(assignX);
    node.x = childXs.reduce((sum, x) => sum + x, 0) / childXs.length;
    return node.x;
  };
  assignX(root);

  // Flatten the tree back into arrays for rendering
  const flatNodes = [];
  const edges = [];
  
  const collect = (node) => {
    flatNodes.push(node);
    node.children.forEach((child) => {
      // Use 'source' and 'target' to match the backend implementation
      edges.push({ 
        source: node.id, 
        target: child.id, 
        relation: 'child' 
      });
      collect(child);
    });
  };
  collect(root);

  return { nodes: flatNodes, edges };
}

/**
 * Local View (Radial) Layout
 * 
 * Places a specific violation's target element at the center (0,0) and arranges 
 * its related nodes in a circular orbit around it.
 * 
 * @param {Object} context - An object containing arrays of related elements.
 * @returns {Object} { nodes, edges } with assigned coordinates.
 */
export function layoutRadialGraph(context) {
  // SAFETY CHECK
  if (!context || !context.target) {
    return { nodes: [], edges: [] };
  }

  const satellites = [];
  
  // Helper to process relationship groups and convert them into standard satellite nodes
  const pushGroup = (items, kind) => {
    (items ?? []).forEach((item, index) => {
      satellites.push({
        id: `${kind}-${index}`,
        label: item.tag ? formatTag(item) : (item.status || "Unknown"),
        note: item.note,
        kind,
        isFlag: !item.tag,
      });
    });
  };

  // Group all relationships
  if (context.parent) pushGroup([context.parent], "parent");
  pushGroup(context.children, "child");
  pushGroup(context.siblings, "sibling");
  pushGroup(context.labelRelationships, "label");
  pushGroup(context.headingRelationships, "heading");
  pushGroup(context.formRelationships, "form");

  // Define the central target node
  const center = { 
    id: "target", 
    label: formatTag(context.target), 
    kind: "target", 
    x: 0, 
    y: 0 
  };
  
  const radius = 1;
  const count = Math.max(satellites.length, 1);
  
  // Calculate polar coordinates for each satellite to form a circle
  const positioned = satellites.map((satellite, index) => {
    const angle = (index / count) * 2 * Math.PI - Math.PI / 2;
    return {
      ...satellite,
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
    };
  });

  // Map edges from the central target to all satellites using 'source' and 'target'
  const edges = positioned.map((satellite) => ({ 
    source: "target", 
    target: satellite.id,
    relation: satellite.kind
  }));

  return { nodes: [center, ...positioned], edges };
}

/**
 * Formats the display label for an HTML element node.
 * 
 * Aligned with backend requirements: This strictly extracts and wraps the tag 
 * name in angle brackets (e.g., "div" becomes "<div>").
 * 
 * @param {Object} node - The node object containing a 'tag' string.
 * @returns {String} The formatted tag label.
 */
function formatTag(node) {
  // SAFETY CHECK: Ensure tag is a valid string before modifying it
  if (!node || !node.tag || typeof node.tag !== 'string') {
    return "<unknown>";
  }
  
  // Return the raw tag wrapped in brackets, stripping out any classes or ids
  return `<${node.tag.toLowerCase()}>`;
}