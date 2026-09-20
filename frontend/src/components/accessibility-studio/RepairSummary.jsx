import StatusBadge from "./StatusBadge.jsx";
import '../../styles/RepairSummary.css';

function RepairSummary({ violation, repair }) {
  if (!violation || !repair) {
    return (
      <section className="repair-summary" aria-label="Generated repair">
        <header className="panel-header">
          <h2>Generated Repair</h2>
        </header>
        <p className="repair-summary__empty">Select a violation to view its generated repair.</p>
      </section>
    );
  }

  return (
    <section className="repair-summary" aria-label="Generated repair">
      <header className="panel-header">
        <h2>Generated Repair</h2>
        <StatusBadge status={repair.status} />
      </header>
      <dl className="repair-summary__grid">
        <div>
          <dt>Violation</dt>
          <dd>
            {violation.id}
            {" \u2014 "}
            {violation.description}
          </dd>
        </div>
        <div>
          <dt>Strategy</dt>
          <dd>{repair.strategy}</dd>
        </div>
        <div>
          <dt>Target element</dt>
          <dd>
            <code>{repair.targetElement}</code>
          </dd>
        </div>
        <div>
          <dt>Generated change</dt>
          <dd>{repair.change}</dd>
        </div>
        <div className="repair-summary__reason">
          <dt>Reason</dt>
          <dd>{repair.reason}</dd>
        </div>
      </dl>
      {repair.relatedRelationships?.length > 0 && (
        <div className="repair-summary__relationships">
          <span>SDG relationships used</span>
          <ul>
            {repair.relatedRelationships.map((relationship) => (
              <li key={relationship}>
                <code>{relationship}</code>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

export default RepairSummary;
