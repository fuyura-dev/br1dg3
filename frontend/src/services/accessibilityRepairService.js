const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

// Keep latest live lookup maps in memory so getSdgContext(id) and getRepair(id)
// resolve directly from the latest backend response.
let liveSdgGraph = {};
let liveRepairs = {};

async function postJson(endpoint, payload) {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let detail = "";
    try {
      const err = await response.json();
      if (err?.detail) detail = `: ${err.detail}`;
    } catch (_) {}
    throw new Error(`Backend returned ${response.status}${detail}`);
  }

  return response.json();
}

function findLineNumber(html, snippet, tag) {
  if (!html) return 1;
  if (snippet) {
    const openTag = snippet.split(">")[0];
    if (openTag) {
      const idx = html.indexOf(openTag);
      if (idx !== -1) {
        return html.slice(0, idx).split("\n").length;
      }
    }
  }
  if (tag) {
    const idx = html.toLowerCase().indexOf(`<${tag.toLowerCase()}`);
    if (idx !== -1) {
      return html.slice(0, idx).split("\n").length;
    }
  }
  return 1;
}

function buildSdgContextForNode(nodeId, nodesById, links, rawContext = null) {
  const targetNode = nodesById.get(nodeId) || { id: nodeId, tag: "unknown", label: `<${nodeId}>` };
  const ctxNodes = rawContext?.nodes?.length ? rawContext.nodes : [targetNode];
  const ctxEdges = rawContext?.edges || [
    ...links.filter((l) => l.source === nodeId || l.target === nodeId),
  ];

  const ctxNodesById = new Map(ctxNodes.map((n) => [n.id, n]));
  const getNodeLabel = (id) => {
    const n = ctxNodesById.get(id) || nodesById.get(id);
    return n?.label || (n?.tag ? `<${n.tag}>` : id);
  };
  const getNodeTag = (id) => {
    const n = ctxNodesById.get(id) || nodesById.get(id);
    return n?.tag || id;
  };

  const describeEdge = (edge) => {
    const srcLabel = getNodeLabel(edge.source);
    const tgtLabel = getNodeLabel(edge.target);
    const derivedSuffix = edge.derived ? " (derived)" : "";
    if (edge.source === nodeId) {
      return {
        tag: getNodeTag(edge.target),
        label: tgtLabel,
        relation: edge.relation,
        derived: Boolean(edge.derived),
        note: `${edge.relation}${derivedSuffix} \u2192 ${tgtLabel}`,
      };
    }
    if (edge.target === nodeId) {
      return {
        tag: getNodeTag(edge.source),
        label: srcLabel,
        relation: edge.relation,
        derived: Boolean(edge.derived),
        note: `${srcLabel} \u2192 ${edge.relation}${derivedSuffix}`,
      };
    }
    return {
      tag: getNodeTag(edge.source),
      label: `${srcLabel} \u2192 ${tgtLabel}`,
      relation: edge.relation,
      derived: Boolean(edge.derived),
      note: `${edge.relation}${derivedSuffix} (ancestor chain)`,
    };
  };

  const pickRelations = (relSet) =>
    ctxEdges.filter((e) => relSet.has(e.relation)).map(describeEdge);

  const structuralRels = pickRelations(
    new Set(["parent_child", "nested_container", "parent_context"])
  );
  const landmarkAndOutlineRels = pickRelations(
    new Set(["landmark_structure", "landmark_context", "heading_hierarchy", "heading_context"])
  );
  const labelAndRefRels = pickRelations(
    new Set([
      "label_input",
      "aria_labelledby",
      "aria_describedby",
      "aria_controls",
      "aria_owns",
      "aria_errormessage",
      "id_reference",
    ])
  );
  const formFocusAndHiddenRels = pickRelations(
    new Set(["form_group", "name_group", "focus_order", "hidden_context"])
  );

  const domPath =
    rawContext?.dom_path?.length > 0
      ? rawContext.dom_path
      : [targetNode.label || `<${targetNode.tag}>`];

  return {
    targetId: nodeId,
    target: {
      tag: targetNode.tag,
      label: targetNode.label || `<${targetNode.tag}>`,
    },
    domPath,
    nodes: ctxNodes,
    links: ctxEdges,
    groups: [
      {
        title: "Structural & Container",
        items: structuralRels,
        emptyLabel: "No structural container edges in subgraph",
      },
      {
        title: "Landmarks & Heading Outline",
        items: landmarkAndOutlineRels,
        emptyLabel: "No landmark or heading outline edges",
      },
      {
        title: "Labels, ARIA & ID References",
        items: labelAndRefRels,
        emptyLabel: "No label, ARIA, or ID reference edges",
      },
      {
        title: "Forms, Focus & Visibility",
        items: formFocusAndHiddenRels,
        emptyLabel: "No form group, focus order, or hiding ancestor edges",
      },
    ],
    // Legacy compatibility fields
    parent: structuralRels[0] || null,
    children: structuralRels.slice(1),
    siblings: [],
    labelRelationships: labelAndRefRels,
    headingRelationships: landmarkAndOutlineRels,
    formRelationships: formFocusAndHiddenRels,
  };
}

function mapMetricsToCards(metricsDict, issuesBefore, issuesAfter) {
  if (!metricsDict) return [];

  const eff = metricsDict.effectiveness || {};
  const saf = metricsDict.safety || {};
  const str = metricsDict.structure || {};
  const efc = metricsDict.efficiency || {};
  const sem = metricsDict.semantic || {};

  const vrScore = Math.max(0, Math.min(100, Math.round(eff.reduction_rate ?? 100)));
  const safetyScore = saf.is_safe ? 100 : 0;
  const structScore = Math.max(0, Math.min(100, Math.round((str.structural_similarity ?? 1) * 100)));
  const cascadeOrAppliedScore =
    efc.total_steps > 0
      ? Math.round(((efc.applied_steps + efc.cascade_resolved_steps) / efc.total_steps) * 100)
      : 100;
  const semScore = Math.max(0, Math.min(100, Math.round(sem.preservation_rate ?? 100)));

  return [
    {
      id: "effectiveness",
      label: "Repair Effectiveness",
      score: vrScore,
      detail: `${eff.violations_resolved ?? issuesBefore - issuesAfter} of ${
        eff.violations_before ?? issuesBefore
      } violations resolved (${issuesAfter} remaining)`,
    },
    {
      id: "safety",
      label: "Repair Safety",
      score: safetyScore,
      detail: saf.is_safe
        ? "Syntactically valid HTML with no truncation or malformed tags"
        : `Safety failed: ${saf.failure_reason || "malformed output"}`,
    },
    {
      id: "structural",
      label: "Structural Preservation",
      score: structScore,
      detail: `Tree similarity ${(str.structural_similarity ?? 1).toFixed(3)} (TED = ${
        str.tree_edit_distance ?? 0
      }, N = ${str.max_tree_size ?? 0})`,
    },
    {
      id: "efficiency",
      label: "Repair Efficiency",
      score: cascadeOrAppliedScore,
      detail: `${efc.api_calls ?? 0} API calls, ${efc.cascade_resolved_steps ?? 0} cascaded, ${
        efc.total_tokens ?? 0
      } tokens`,
    },
    {
      id: "semantic",
      label: "Semantic Dependency Preservation",
      score: semScore,
      detail: `${sem.dependencies_valid ?? 0} of ${
        sem.dependencies_before ?? 0
      } SDG relationships preserved`,
    },
  ];
}

let lastScannedHtml = null;
let lastGraphRes = null;

function buildWorkspaceData(html, graphRes, repairRes = null) {
  const rawNodes = graphRes.nodes || [];
  const rawLinks = graphRes.links || [];
  const nodesById = new Map(rawNodes.map((n) => [n.id, n]));

  const stepsByOrigNodeId = new Map();
  if (repairRes?.steps) {
    for (const step of repairRes.steps) {
      if (step.original_node_id) {
        stepsByOrigNodeId.set(step.original_node_id, step);
      }
    }
  }

  const mappedViolations = [];
  const newSdgGraph = {};
  const newRepairs = {};
  const nodeViolationMap = new Map();

  let vIndex = 1;
  for (const node of rawNodes) {
    if (!node.has_issue || !node.issues?.length) continue;

    const vId = `V${String(vIndex).padStart(3, "0")}`;
    vIndex += 1;
    nodeViolationMap.set(node.id, vId);

    const step = stepsByOrigNodeId.get(node.id);
    const primaryIssue = node.issues[0];
    const allRules = node.issues.map((i) => i.id).join(", ");
    const impact = primaryIssue.impact || "moderate";
    const snippet = primaryIssue.html || `<${node.tag}>`;

    const rawStatus = step?.status || "open";
    const normalizedStatus =
      rawStatus === "applied" || rawStatus === "cascade_resolved"
        ? "applied"
        : rawStatus.startsWith("llm_") || rawStatus === "empty_reply"
        ? "failed"
        : "open";

    mappedViolations.push({
      id: vId,
      nodeId: node.id,
      ruleId: allRules,
      wcag: allRules,
      impact,
      severity: impact,
      target: `<${node.tag}> (${node.id})`,
      element: `<${node.tag}>`,
      line: findLineNumber(html, snippet, node.tag),
      html: snippet,
      description: node.issues.map((i) => i.help || i.description || i.id).join("; "),
      failureSummary: primaryIssue.description || primaryIssue.help || "",
      status: normalizedStatus,
    });

    newSdgGraph[vId] = buildSdgContextForNode(
      node.id,
      nodesById,
      rawLinks,
      graphRes.contexts?.[node.id] || null
    );

    if (step) {
      const isCascade = step.status === "cascade_resolved";
      newRepairs[vId] = {
        strategy: isCascade
          ? `Cascade Resolution (${step.rules.join(", ")})`
          : `SDG-Guided LLM Repair (${step.rules.join(", ")})`,
        change: isCascade
          ? "Resolved automatically by an ancestor landmark/container patch without an extra LLM call."
          : step.repaired_html || "Applied structural patch to element.",
        targetElement: `<${node.tag}> (${node.id})`,
        reason: isCascade
          ? "Topological dependency ordering repaired the enclosing ancestor first, satisfying this element's requirement automatically."
          : `Patched using localized SDG subgraph context (${step.related_relationships?.length || 0} dependency edges).`,
        relatedRelationships: step.related_relationships || [],
        status: normalizedStatus,
      };
    } else {
      newRepairs[vId] = {
        strategy: `Pending SDG-Guided Repair (${allRules})`,
        change: repairRes
          ? "No patch recorded."
          : "Click 'Run Repair' to generate an SDG-guided patch for this violation.",
        targetElement: `<${node.tag}> (${node.id})`,
        reason: primaryIssue.description || primaryIssue.help || "",
        relatedRelationships: [],
        status: "open",
      };
    }
  }

  const mappedDocumentGraph = {
    nodes: rawNodes.map((n) => ({
      ...n,
      violationId: nodeViolationMap.get(n.id) || null,
    })),
    links: rawLinks,
  };

  const mappedMetrics = repairRes
    ? mapMetricsToCards(repairRes.metrics, repairRes.issues_before, repairRes.issues_after)
    : [];

  liveSdgGraph = newSdgGraph;
  liveRepairs = newRepairs;

  return {
    htmlSource: html,
    repairedHtml: repairRes ? repairRes.fixed_html || html : "",
    violations: mappedViolations,
    documentGraph: mappedDocumentGraph,
    sdgGraph: newSdgGraph,
    repairs: newRepairs,
    evaluationMetrics: mappedMetrics,
  };
}

export const accessibilityRepairService = {
  async scanHtml(html) {
    const graphRes = await postJson("/graph", { html });
    lastScannedHtml = html;
    lastGraphRes = graphRes;
    return buildWorkspaceData(html, graphRes, null);
  },

  async repairHtml(html) {
    const needsGraph = lastScannedHtml !== html || !lastGraphRes;
    const [graphRes, repairRes] = await Promise.all([
      needsGraph ? postJson("/graph", { html }) : Promise.resolve(lastGraphRes),
      postJson("/repair", { html, use_sdg: true }),
    ]);
    lastScannedHtml = html;
    lastGraphRes = graphRes;
    return buildWorkspaceData(html, graphRes, repairRes);
  },

  async getSdgContext(violationId) {
    return liveSdgGraph[violationId] ?? null;
  },

  async getRepair(violationId) {
    return liveRepairs[violationId] ?? null;
  },
};
