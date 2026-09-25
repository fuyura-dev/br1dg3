import ViolationItem from "./ViolationItem.jsx";
import '../../styles/ViolationsPanel.css';

function ViolationsPanel({ violations, selectedId, onSelect }) {
  return (
    <section className="violations-panel" aria-label="Detected violations">
      <header className="panel-header">
        <h2>Detected Violations</h2>
        <span className="panel-header__count">{violations.length} found</span>
      </header>
      {violations.length === 0 ? (
        <p style={{ color: "var(--color-text-tertiary)", fontSize: "13px", margin: 0 }}>
          No violations loaded. Enter HTML in the editor and click Run Scan.
        </p>
      ) : (
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
      )}
    </section>
  );
}

export default ViolationsPanel;
