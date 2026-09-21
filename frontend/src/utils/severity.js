export const SEVERITY_META = {
  critical: { label: "Critical", color: "var(--color-critical)", soft: "var(--color-critical-soft)" },
  serious: { label: "Serious", color: "var(--color-warning)", soft: "var(--color-warning-soft)" },
  moderate: { label: "Moderate", color: "var(--color-moderate)", soft: "var(--color-moderate-soft)" },
  minor: { label: "Minor", color: "var(--color-minor)", soft: "var(--color-minor-soft)" },
};

export function getSeverityMeta(severity) {
  return SEVERITY_META[severity] ?? SEVERITY_META.minor;
}

export const STATUS_META = {
  completed: { label: "Completed", color: "var(--color-success)", soft: "var(--color-success-soft)" },
  active: { label: "In progress", color: "var(--color-accent)", soft: "var(--color-accent-soft)" },
  pending: { label: "Pending", color: "var(--color-text-secondary)", soft: "var(--color-minor-soft)" },
  failed: { label: "Failed", color: "var(--color-critical)", soft: "var(--color-critical-soft)" },
  open: { label: "Open", color: "var(--color-warning)", soft: "var(--color-warning-soft)" },
  applied: { label: "Applied", color: "var(--color-success)", soft: "var(--color-success-soft)" },
};

export function getStatusMeta(status) {
  return STATUS_META[status] ?? { label: status, color: "var(--color-text-secondary)", soft: "var(--color-minor-soft)" };
}
