import React from 'react';
import SeverityBadge from "./SeverityBadge.jsx";
import StatusBadge from "./StatusBadge.jsx";
import '../../styles/ViolationsPanel.css';

function ViolationItem({ violation, isSelected, onSelect }) {
  // Map severity to CSS class modifier
  const severityClass = violation.severity.toLowerCase();
  
  return (
    <li>
      <button
        type="button"
        className={`violation-card violation-card--${severityClass}${isSelected ? " is-selected" : ""}`}
        onClick={() => onSelect(violation.id)}
        aria-pressed={isSelected}
      >
        <div className="violation-card__indicator"></div>
        
        <div className="violation-card__content">
          <div className="violation-card__header">
            <div className="violation-card__tags">
              <SeverityBadge severity={violation.severity} />
              <span className="violation-card__wcag">WCAG {violation.wcag}</span>
            </div>
            <StatusBadge status={violation.status} />
          </div>
          
          <h3 className="violation-card__title">{violation.description}</h3>
          
          <div className="violation-card__details">
            <div className="violation-card__code">
              <code>{violation.element}</code>
            </div>
            <div className="violation-card__line">Line {violation.line}</div>
          </div>
          
          <div className="violation-card__action">
            <span className="action-text">Review SDG impact & recommended fix &rarr;</span>
          </div>
        </div>
      </button>
    </li>
  );
}

export default ViolationItem;
