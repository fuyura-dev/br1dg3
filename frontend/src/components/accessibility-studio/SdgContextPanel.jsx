import { formatNodeLabel } from "../../utils/format.js";
import "../../styles/SdgContextPanel.css";

function RelationshipGroup({ title, items, emptyLabel }) {
  return (
    <div className="sdg-group">
      <h3>{title}</h3>
      {!items || items.length === 0 ? (
        <p className="sdg-group__empty">{emptyLabel}</p>
      ) : (
        <ul>
          {items.map((item, index) => (
            <li key={index} className="sdg-node">
              {item.label || item.tag ? (
                <code>{item.label || formatNodeLabel(item)}</code>
              ) : (
                <span className={`sdg-node__flag sdg-node__flag--${item.status}`}>
                  {item.status}
                </span>
              )}
              {item.note && <span className="sdg-node__note">{item.note}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SdgContextPanel({ violation, context, onOpenGraph }) {
  if (!violation || !context) {
    return (
      <section className="sdg-panel" aria-label="Structural dependency graph context">
        <header className="panel-header">
          <h2>SDG Context</h2>
          <button type="button" className="sdg-panel__graph-btn" onClick={onOpenGraph}>
            View SDG Graph
          </button>
        </header>
        <p className="sdg-panel__empty">
          Select a violation to inspect its structural dependencies.
        </p>
      </section>
    );
  }

  const groups = context.groups || [
    {
      title: "Parent",
      items: context.parent ? [context.parent] : [],
      emptyLabel: "No parent recorded",
    },
    {
      title: "Children",
      items: context.children,
      emptyLabel: "No child elements",
    },
    {
      title: "Label relationships",
      items: context.labelRelationships,
      emptyLabel: "No label relationship affected",
    },
    {
      title: "Heading relationships",
      items: context.headingRelationships,
      emptyLabel: "No heading relationship affected",
    },
    {
      title: "Form relationships",
      items: context.formRelationships,
      emptyLabel: "No form relationship affected",
    },
  ];

  return (
    <section className="sdg-panel" aria-label="Structural dependency graph context">
      <header className="panel-header">
        <h2>SDG Context</h2>
        <div className="sdg-panel__header-actions">
          <span className="panel-header__count">{violation.id}</span>
          <button type="button" className="sdg-panel__graph-btn" onClick={onOpenGraph}>
            View SDG Graph
          </button>
        </div>
      </header>

      <div className="sdg-panel__target">
        <span>Target element</span>
        <code>{context.target?.label || formatNodeLabel(context.target)}</code>
      </div>

      {context.domPath?.length > 0 && (
        <nav className="sdg-breadcrumb" aria-label="DOM hierarchy">
          {context.domPath.map((step, index) => (
            <span key={index} className="sdg-breadcrumb__step">
              {step}
              {index < context.domPath.length - 1 && (
                <span aria-hidden="true">{" \u203a "}</span>
              )}
            </span>
          ))}
        </nav>
      )}

      <div className="sdg-panel__groups">
        {groups.map((group) => (
          <RelationshipGroup
            key={group.title}
            title={group.title}
            items={group.items}
            emptyLabel={group.emptyLabel}
          />
        ))}
      </div>
    </section>
  );
}

export default SdgContextPanel;
