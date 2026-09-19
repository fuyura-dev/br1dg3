export function formatPercentage(value) {
  return `${Math.round(value)}%`;
}

// Thresholds reflect how the study's five dependent variables are read
// during manual review, not a formal grading scale.
export function scoreStatus(score) {
  if (score >= 90) return { label: "Excellent", tone: "success" };
  if (score >= 75) return { label: "Good", tone: "accent" };
  if (score >= 60) return { label: "Fair", tone: "warning" };
  return { label: "Needs review", tone: "critical" };
}

// Renders a DOM node descriptor such as { tag: "input", id: "email" }
// as a CSS-selector-style label, e.g. "input#email.field".
export function formatNodeLabel(node) {
  if (!node || !node.tag) return "";
  let label = node.tag;
  if (node.id) label += `#${node.id}`;
  if (node.classes?.length) label += `.${node.classes.join(".")}`;
  return label;
}
