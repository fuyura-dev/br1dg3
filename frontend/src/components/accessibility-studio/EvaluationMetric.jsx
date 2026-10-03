import { formatPercentage, scoreStatus } from "../../utils/format.js";

const METRIC_ACCENT_VAR = {
  effectiveness: "--metric-effectiveness",
  safety: "--metric-safety",
  structural: "--metric-structural",
  efficiency: "--metric-efficiency",
  semantic: "--metric-semantic",
};

function EvaluationMetric({ metric }) {
  const status = metric.status || scoreStatus(metric.score);
  const accentVar = METRIC_ACCENT_VAR[metric.id] ?? "--color-accent";
  const displayScore =
    metric.displayValue !== undefined
      ? metric.displayValue
      : formatPercentage(metric.score);

  return (
    <article className="evaluation-metric" style={{ "--metric-accent": `var(${accentVar})` }}>
      <div className="evaluation-metric__top">
        <span className="evaluation-metric__dot" aria-hidden="true" />
        <span className={`evaluation-metric__status evaluation-metric__status--${status.tone}`}>
          {status.label}
        </span>
      </div>
      <h3 className="evaluation-metric__label">{metric.label}</h3>
      <p className="evaluation-metric__score">{displayScore}</p>
      {metric.showBar !== false && typeof metric.score === "number" && (
        <div
          className="evaluation-metric__bar"
          role="progressbar"
          aria-valuenow={metric.score}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={metric.label}
        >
          <div
            className="evaluation-metric__bar-fill"
            style={{ width: `${Math.max(0, Math.min(100, metric.score))}%` }}
          />
        </div>
      )}
      {metric.stats && metric.stats.length > 0 && (
        <div className="evaluation-metric__stats">
          {metric.stats.map((stat, idx) => (
            <span key={idx} className="evaluation-metric__stat-badge">
              <strong>{stat.value}</strong> {stat.label}
            </span>
          ))}
        </div>
      )}
      {metric.detail && <p className="evaluation-metric__detail">{metric.detail}</p>}
    </article>
  );
}

export default EvaluationMetric;
