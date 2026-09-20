import { formatNodeLabel } from "../../utils/format.js";
import '../../styles/SdgContextPanel.css';

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
              {item.tag ? (
                <code>{formatNodeLabel(item)}</code>
              ) : (
                <span className={`sdg-node__flag sdg-node__flag--${item.status}`}>{item.status}</span>
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
        <p className="sdg-panel__empty">Select a violation to inspect its structural dependencies.</p>
      </section>
    );
  }

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
        <code>{formatNodeLabel(context.target)}</code>
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
        <RelationshipGroup title="Parent" items={context.parent ? [context.parent] : []} emptyLabel="No parent recorded" />
        <RelationshipGroup title="Children" items={context.children} emptyLabel="No child elements" />
        <RelationshipGroup title="Siblings" items={context.siblings} emptyLabel="No related siblings" />
        <RelationshipGroup
          title="Label relationships"
          items={context.labelRelationships}
          emptyLabel="No label relationship affected"
        />
        <RelationshipGroup
          title="Heading relationships"
          items={context.headingRelationships}
          emptyLabel="No heading relationship affected"
        />
        <RelationshipGroup
          title="Form relationships"
          items={context.formRelationships}
          emptyLabel="No form relationship affected"
        />
      </div>
    </section>
  );
}

export default SdgContextPanel;
