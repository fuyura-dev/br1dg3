import React from 'react';
import EvaluationMetric from "./EvaluationMetric.jsx";
import '../../styles/EvaluationSummary.css';

function EvaluationSummary({ metrics }) {
  if (!metrics || metrics.length === 0) return null;

  return (
    <section className="evaluation-summary" aria-label="Validation and evaluation summary">
      <header className="panel-header">
        <h2>Validation &amp; Evaluation Summary</h2>
      </header>
      <div className="evaluation-summary__grid">
        {metrics.map((metric) => (
          <EvaluationMetric key={metric.id} metric={metric} />
        ))}
      </div>
    </section>
  );
}

export default React.memo(EvaluationSummary);
