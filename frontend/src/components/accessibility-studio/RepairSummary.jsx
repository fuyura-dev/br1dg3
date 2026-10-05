import React from 'react';
import StatusBadge from "./StatusBadge.jsx";
import '../../styles/RepairSummary.css';

const IconWrench = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

const IconCode = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="16 18 22 12 16 6"></polyline>
    <polyline points="8 6 2 12 8 18"></polyline>
  </svg>
);

const IconAlert = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="12" y1="8" x2="12" y2="12"></line>
    <line x1="12" y1="16" x2="12.01" y2="16"></line>
  </svg>
);

const IconSparkles = () => (
  <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"></path>
  </svg>
);

function RepairSummary({ violation, repair }) {
  if (!violation || !repair) {
    const emptyText = violation 
      ? "Run AI Repair to generate a fix for this violation."
      : "Select a violation from the list to view its AI-generated repair magic.";
      
    return (
      <section className="repair-summary repair-summary--empty" aria-label="Generated repair">
        <div className="repair-summary__empty-content">
          <IconSparkles />
          <p>{emptyText}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="repair-summary" aria-label="Generated repair">
      <header className="repair-summary__header">
        <div className="repair-summary__title">
          <div className="repair-summary__title-icon">
            <IconSparkles />
          </div>
          <h2>Generated Repair</h2>
        </div>
        <StatusBadge status={repair.status} />
      </header>
      
      <div className="repair-summary__cards">
        <div className="repair-card repair-card--violation">
          <div className="repair-card__header">
            <IconAlert />
            <dt>Violation</dt>
          </div>
          <dd>
            <span className="violation-id">{violation.id}</span>
            <span className="violation-desc">{violation.description}</span>
          </dd>
        </div>
        
        <div className="repair-card repair-card--strategy">
          <div className="repair-card__header">
            <IconWrench />
            <dt>Strategy</dt>
          </div>
          <dd>{repair.strategy}</dd>
        </div>
        
        <div className="repair-card repair-card--target">
          <div className="repair-card__header">
            <IconCode />
            <dt>Target Element</dt>
          </div>
          <dd>
            <code>{repair.targetElement}</code>
          </dd>
        </div>
        
        <div className="repair-card repair-card--change">
          <div className="repair-card__header">
            <IconCode />
            <dt>Generated Change</dt>
          </div>
          <dd className="code-change">
            <code>{repair.change}</code>
          </dd>
        </div>
        
        <div className="repair-card repair-card--reason">
          <div className="repair-card__header">
            <IconSparkles />
            <dt>Reason</dt>
          </div>
          <dd>{repair.reason}</dd>
        </div>
      </div>
      
      {repair.relatedRelationships?.length > 0 && (
        <div className="repair-summary__footer">
          <span className="footer-label">SDG Context Utilized:</span>
          <div className="footer-chips">
            {repair.relatedRelationships.map((relationship, idx) => (
              <div key={idx} className="relationship-chip">
                {relationship}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default React.memo(RepairSummary);
