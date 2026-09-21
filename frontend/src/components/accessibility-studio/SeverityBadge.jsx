import { getSeverityMeta } from "../../utils/severity.js";

function SeverityBadge({ severity }) {
  const meta = getSeverityMeta(severity);
  return (
    <span className="badge" style={{ color: meta.color, backgroundColor: meta.soft }}>
      {meta.label}
    </span>
  );
}

export default SeverityBadge;
