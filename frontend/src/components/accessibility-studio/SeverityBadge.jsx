import React from 'react';

const SeverityBadge = ({ severity }) => {
  let badgeColor = '';
  
  switch (severity?.toLowerCase()) {
    case 'critical':
      badgeColor = 'var(--color-critical)';
      break;
    case 'serious':
      badgeColor = 'var(--color-warning)';
      break;
    case 'moderate':
      badgeColor = 'var(--color-moderate)';
      break;
    case 'minor':
      badgeColor = 'var(--color-minor)';
      break;
    default:
      badgeColor = 'var(--color-text-secondary)';
  }

  // Inject a dynamic style overriding the CSS variable for the badge's background and text
  const badgeStyle = {
    backgroundColor: `color-mix(in srgb, ${badgeColor} 15%, transparent)`,
    color: badgeColor,
    border: `1px solid color-mix(in srgb, ${badgeColor} 30%, transparent)`,
    padding: '4px 10px',
    borderRadius: '6px',
    fontWeight: '700',
    fontSize: '12px',
    textTransform: 'uppercase',
    letterSpacing: '0.04em'
  };

  return (
    <span className="badge badge--severity" style={badgeStyle}>
      {severity}
    </span>
  );
};

export default SeverityBadge;
