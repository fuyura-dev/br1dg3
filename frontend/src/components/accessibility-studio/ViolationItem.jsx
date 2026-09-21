import SeverityBadge from "./SeverityBadge.jsx";
import StatusBadge from "./StatusBadge.jsx";

function ViolationItem({ violation, isSelected, onSelect }) {
  return (
    <li>
      <button
        type="button"
        className={`violation-item${isSelected ? " violation-item--selected" : ""}`}
        onClick={() => onSelect(violation.id)}
        aria-pressed={isSelected}
      >
        <div className="violation-item__top">
          <SeverityBadge severity={violation.severity} />
          <span className="violation-item__wcag">WCAG {violation.wcag}</span>
        </div>
        <p className="violation-item__description">{violation.description}</p>
        <div className="violation-item__meta">
          <code>{violation.element}</code>
          <span>Line {violation.line}</span>
        </div>
        <div className="violation-item__footer">
          <StatusBadge status={violation.status} />
        </div>
      </button>
    </li>
  );
}

export default ViolationItem;
