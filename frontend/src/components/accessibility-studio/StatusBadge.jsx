import { getStatusMeta } from "../../utils/severity.js";

function StatusBadge({ status }) {
  const meta = getStatusMeta(status);
  return (
    <span className="badge" style={{ color: meta.color, backgroundColor: meta.soft }}>
      {meta.label}
    </span>
  );
}

export default StatusBadge;
