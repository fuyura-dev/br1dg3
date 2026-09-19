import ViolationItem from "./ViolationItem.jsx";
import "./ViolationsPanel.css";

function ViolationsPanel({ violations, selectedId, onSelect }) {
  return (
    <section className="violations-panel" aria-label="Detected violations">
      <header className="panel-header">
        <h2>Detected Violations</h2>
        <span className="panel-header__count">{violations.length} found</span>
      </header>
      <ul className="violations-panel__list">
        {violations.map((violation) => (
          <ViolationItem
            key={violation.id}
            violation={violation}
            isSelected={violation.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </section>
  );
}

export default ViolationsPanel;
