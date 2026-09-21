/**
 * Graph Data Parser Utilities
 * 
 * Re-architected for Directed Graphs with multi-parent and cycle support.
 * Maps the API schema ({ nodes, links }) directly to ForceGraph2D expectations.
 */

export function layoutDocumentTree(documentGraph) {
  if (!documentGraph || !Array.isArray(documentGraph.nodes)) {
    return { nodes: [], links: [] };
  }

  // Pinapanatili natin ang schema na ibinabato ng API.
  // Ang react-force-graph-2d na ang bahalang mag-layout ng cycles at multi-parents.
  return {
    nodes: documentGraph.nodes.map(n => ({ ...n, id: String(n.id) })),
    links: (documentGraph.links || []).map(l => ({ 
      source: String(l.source), 
      target: String(l.target), 
      relation: l.relation 
    }))
  };
}

export function layoutRadialGraph(context) {
  if (!context || !context.target) {
    return { nodes: [], links: [] };
  }

  const nodes = [];
  const links = [];
  
  const pushGroup = (items, relation) => {
    const list = Array.isArray(items) ? items : (items ? [items] : []);
    list.forEach((item, index) => {
      const satId = `${relation}-${index}`;
      nodes.push({
        id: satId,
        tag: item.tag || null,
        label: item.tag ? formatTag(item) : (item.status || "Unknown"),
        note: item.note,
        kind: relation,
        isFlag: !item.tag,
      });

      // Ginagawang explicit link arrays ang mga context properties
      links.push({ 
        source: "target", 
        target: satId,
        relation: relation
      });
    });
  };

  // Center Target
  nodes.push({ 
    id: "target", 
    tag: context.target.tag,
    label: formatTag(context.target), 
    kind: "target" 
  });

  pushGroup(context.parent, "parent");
  pushGroup(context.children, "child");
  pushGroup(context.siblings, "sibling");
  pushGroup(context.labelRelationships, "label");
  pushGroup(context.headingRelationships, "heading");
  pushGroup(context.formRelationships, "form");

  return { nodes, links };
}

function formatTag(node) {
  if (!node || !node.tag || typeof node.tag !== 'string') return "<unknown>";
  return `<${node.tag.toLowerCase()}>`;
}