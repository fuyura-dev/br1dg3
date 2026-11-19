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

function findLineNumber(html, snippet, tag, occurrence = 1) {
  if (!html) return 1;
  
  let searchStr = "";
  if (snippet) {
    searchStr = snippet.split(">")[0];
  } else if (tag) {
    searchStr = `<${tag.toLowerCase()}`;
  }
  
  if (!searchStr) return 1;
  
  let idx = -1;
  for (let i = 0; i < occurrence; i++) {
    idx = html.toLowerCase().indexOf(searchStr.toLowerCase(), idx + 1);
    if (idx === -1) {
      // If we can't find the Nth occurrence, fallback to the last found index or 0
      break;
    }
  }
  
  if (idx !== -1) {
    return html.slice(0, idx).split("\n").length;
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
  const noCandidate = metricsDict.evaluation?.score_basis === "no_candidate_failure_policy";

  // 1. Repair Effectiveness (CIR, FFR, Reduction Rate)
  const fallbackReduction =
    issuesBefore > 0
      ? Math.round(((issuesBefore - issuesAfter) / issuesBefore) * 100)
      : 100;
  const vrScore = Math.max(
    0,
    Math.min(100, Math.round(eff.reduction_rate ?? fallbackReduction))
  );
  const isFullyFixed = Boolean(eff.fully_fixed ?? (issuesAfter === 0));
  const isImproved = Boolean(eff.compliance_improved ?? (issuesAfter < issuesBefore));
  const effectivenessStatus = isFullyFixed
    ? { label: "Fully Fixed (Selected Rules)", tone: "success" }
    : isImproved
    ? { label: "Improved", tone: "accent" }
    : { label: "No Change", tone: "warning" };

  const violationsReduced =
    eff.violations_reduced ?? Math.max(0, issuesBefore - issuesAfter);
  const totalBefore = eff.violations_before ?? issuesBefore;
  const totalAfter = eff.violations_after ?? issuesAfter;

  // 2. Repair Safety (Syntactic Validity Si in {0, 1})
  const isValid = Boolean(saf.is_valid);
  const safetyUnavailable = saf.reason === "validator_error";
  const safetyScore = safetyUnavailable ? null : isValid ? 100 : 0;
  const safetyStatus = safetyUnavailable
    ? { label: "Check Unavailable", tone: "warning" }
    : isValid
    ? { label: "No Parsing Errors", tone: "success" }
    : { label: "Validity Check Failed", tone: "critical" };
  const firstParseError = saf.errors?.[0];
  const safetyDetail = safetyUnavailable
    ? "The HTML checker failed to run. No validity score is assigned; retry evaluation."
    : isValid
    ? "No HTML parsing errors found. This does not establish full HTML conformance."
    : firstParseError
    ? `${saf.error_count} HTML parsing error(s). First: ${firstParseError.message} (line ${firstParseError.line}, column ${firstParseError.column}).`
    : `Validity check failed: ${saf.reason || "unusable HTML output"}`;

  // 3. Structural Preservation (Zhang-Shasha TED, SS_i >= 0.85)
  const sim = str.structure_similarity ?? 1;
  const structScore = Math.max(0, Math.min(100, Math.round(sim * 100)));
  const isPreserved = Boolean(
    str.structure_preserved ?? sim >= (str.threshold ?? 0.85)
  );
  const structStatus = isPreserved
    ? { label: "Preserved (≥0.85)", tone: "success" }
    : { label: "Altered (<0.85)", tone: "warning" };

  // 4. Repair Efficiency (Resource metrics: TAC, TT, TC, Cascaded)
  const apiCalls = efc.api_calls ?? 0;
  const totalTokens = efc.total_tokens ?? 0;
  const costUsd = efc.cost_usd ?? 0;
  const cascadedCount = efc.cascaded_count ?? 0;
  const totalElements = efc.total_elements ?? 0;
  const cascadeRate = efc.cascade_rate ?? 0;

  const efficiencyStatus =
    cascadedCount > 0
      ? { label: `${cascadedCount} Locally Skipped`, tone: "accent" }
      : { label: "Completed", tone: "accent" };

  // 5. Semantic Dependency Preservation (SDP_i)
  const hasDeps = Boolean(sem.has_dependencies);
  const semRate = sem.preservation_rate ?? 100;
  const semScore = Math.max(0, Math.min(100, Math.round(semRate)));
  const brokenCount = sem.broken_count ?? 0;
  const validDeps = sem.dependencies_valid ?? 0;
  const totalDeps = sem.dependencies_before ?? 0;

  let semanticStatus;
  if (!hasDeps) {
    semanticStatus = { label: "N/A (No Dependencies)", tone: "accent" };
  } else if (semRate === 100) {
    semanticStatus = { label: "100% Intact", tone: "success" };
  } else if (semRate >= 80) {
    semanticStatus = { label: "Mostly Intact", tone: "accent" };
  } else {
    semanticStatus = { label: `${brokenCount} Broken`, tone: "warning" };
  }

  const cards = [
    {
      id: "effectiveness",
      label: "Repair Effectiveness",
      score: vrScore,
      status: effectivenessStatus,
      detail: `${violationsReduced} of ${totalBefore} selected-rule violations reduced (${totalAfter} confirmed remaining). Results needing review are separate from this count.`,
    },
    {
      id: "safety",
      label: "Repair Safety",
      score: safetyScore,
      displayValue: safetyUnavailable ? "N/A" : isValid ? "Valid" : "Invalid",
      showBar: !safetyUnavailable,
      status: safetyStatus,
      detail: safetyDetail,
    },
    {
      id: "structural",
      label: "Structural Preservation",
      score: structScore,
      displayValue: sim.toFixed(3),
      status: structStatus,
      detail: `TED = ${str.tree_edit_distance ?? 0} edits on max ${
        str.max_nodes ?? 0
      } DOM nodes (Threshold θ = ${str.threshold ?? 0.85})`,
    },
    {
      id: "efficiency",
      label: "Repair Efficiency",
      showBar: false,
      displayValue: `${apiCalls} API Call${apiCalls === 1 ? "" : "s"}`,
      status: efficiencyStatus,
      stats: [
        { value: `${apiCalls}`, label: "calls" },
        { value: totalTokens.toLocaleString(), label: "tokens" },
        { value: `$${costUsd.toFixed(5)}`, label: "USD" },
      ],
      detail: `${totalTokens.toLocaleString()} tokens ($${costUsd.toFixed(
        5
      )} USD) · ${cascadedCount} of ${totalElements} scheduled targets locally skipped (${cascadeRate}%). Skips are not individually Axe-verified.`,
    },
    {
      id: "semantic",
      label: "Semantic Dependency Preservation",
      score: semScore,
      status: semanticStatus,
      detail: hasDeps
        ? `${validDeps} of ${totalDeps} relationships intact (${brokenCount} broken)`
        : "No semantic relationships present in document",
    },
  ];

  if (noCandidate) {
    for (const card of cards) {
      if (card.id === "efficiency") {
        card.status = { label: "Available Usage", tone: "accent" };
        continue;
      }
      if (card.id === "semantic" && !hasDeps) {
        card.displayValue = "N/A";
        card.showBar = false;
        continue;
      }
      card.score = 0;
      card.displayValue = "No credit";
      card.status = { label: "No Repair Candidate", tone: "warning" };
      card.detail = "No accepted repair was produced. Zero credit is assigned; the returned fallback HTML was not scored.";
    }
  }
  return cards;
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
  const occurrenceMap = new Map();

  let vIndex = 1;
  for (const node of rawNodes) {
    // Track the occurrence of the raw tag across ALL elements (healthy or not)
    // so we maintain exact sync with the raw HTML string's document order.
    const tagSearchStr = `<${node.tag.toLowerCase()}`;
    const tagOccurrence = (occurrenceMap.get(tagSearchStr) || 0) + 1;
    occurrenceMap.set(tagSearchStr, tagOccurrence);

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
    const isCascade = rawStatus === "cascade_skipped" || rawStatus === "cascade_resolved";
    const normalizedStatus =
      rawStatus === "applied"
        ? "applied"
        : isCascade
        ? "skipped"
        : rawStatus.startsWith("llm_") || ["empty_reply", "tracking_rejected", "patch_rejected", "prompt_too_large"].includes(rawStatus)
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
      // Always use the exact tag occurrence for reliable line matching
      line: findLineNumber(html, null, node.tag, tagOccurrence),
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
      const skippedRules = step.skipped_rules || [];
      const skipDetails = skippedRules.map((item) => `${item.rule_id}: ${item.reason}`).join("; ");
      const requestedRules = step.requested_rules ?? step.rules;
      const patchRejected = step.status === "tracking_rejected" || step.status === "patch_rejected";
      const promptTooLarge = step.status === "prompt_too_large";
      newRepairs[vId] = {
        strategy: promptTooLarge
          ? "Repair not generated"
          : isCascade
          ? `Local Cascade Skip (${step.rules.join(", ")})`
          : `SDG-Guided LLM Repair (${requestedRules.join(", ")})`,
        change: promptTooLarge
          ? "No model call; previous HTML retained."
          : patchRejected
          ? "Patch rejected; previous HTML retained."
          : isCascade
          ? "No LLM call for this target; skipped by a local HTML check."
          : step.repaired_html || "Applied structural patch to element.",
        targetElement: `<${node.tag}> (${node.id})`,
        reason: promptTooLarge
          ? "Root markup exceeded the configured size limit."
          : patchRejected
          ? step.status === "tracking_rejected"
            ? "The proposed repair could not preserve unambiguous element tracking."
            : "The proposed repair could not be reconstructed unambiguously; the previous HTML was retained."
          : isCascade
          ? `${skipDetails || "Historical local skip; no detailed evidence recorded."} This skip was not individually verified by Axe.`
          : `Patched using localized SDG subgraph context (${step.related_relationships?.length || 0} dependency edges).${skipDetails ? ` Locally skipped rules: ${skipDetails} These skips were not individually verified by Axe.` : ""}`,
        skippedRules,
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
