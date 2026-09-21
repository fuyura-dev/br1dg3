import EvaluationMetric from "./EvaluationMetric.jsx";
import '../../styles/EvaluationSummary.css';

function EvaluationSummary({ metrics }) {
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

export default EvaluationSummary;
