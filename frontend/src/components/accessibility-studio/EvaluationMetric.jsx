import { formatPercentage, scoreStatus } from "../../utils/format.js";

const METRIC_ACCENT_VAR = {
  effectiveness: "--metric-effectiveness",
  safety: "--metric-safety",
  structural: "--metric-structural",
  efficiency: "--metric-efficiency",
  semantic: "--metric-semantic",
};

function EvaluationMetric({ metric }) {
  const status = scoreStatus(metric.score);
  const accentVar = METRIC_ACCENT_VAR[metric.id] ?? "--color-accent";

  return (
    <article className="evaluation-metric" style={{ "--metric-accent": `var(${accentVar})` }}>
      <div className="evaluation-metric__top">
        <span className="evaluation-metric__dot" aria-hidden="true" />
        <span className={`evaluation-metric__status evaluation-metric__status--${status.tone}`}>
          {status.label}
        </span>
      </div>
      <h3 className="evaluation-metric__label">{metric.label}</h3>
      <p className="evaluation-metric__score">{formatPercentage(metric.score)}</p>
      <div
        className="evaluation-metric__bar"
        role="progressbar"
        aria-valuenow={metric.score}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={metric.label}
      >
        <div className="evaluation-metric__bar-fill" style={{ width: `${metric.score}%` }} />
      </div>
      {metric.detail && <p className="evaluation-metric__detail">{metric.detail}</p>}
    </article>
  );
}

export default EvaluationMetric;
