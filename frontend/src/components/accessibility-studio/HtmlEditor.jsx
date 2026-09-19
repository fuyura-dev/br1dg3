import { tokenizeHtmlLine } from "../../utils/highlightHtml.js";
import "./HtmlEditor.css";

function HtmlEditor({ title, code, highlightedLine }) {
  const lines = code.split("\n");

  return (
    <section className="html-editor" aria-label={title}>
      <header className="panel-header">
        <h2>{title}</h2>
        <span className="html-editor__tag">HTML</span>
      </header>
      <pre className="html-editor__code">
        {lines.map((line, index) => {
          const lineNumber = index + 1;
          const tokens = tokenizeHtmlLine(line);
          const isActive = lineNumber === highlightedLine;
          return (
            <div
              key={lineNumber}
              className={`html-editor__line${isActive ? " html-editor__line--active" : ""}`}
            >
              <span className="html-editor__line-number">{lineNumber}</span>
              <span className="html-editor__line-content">
                {tokens.length === 0
                  ? "\u00A0"
                  : tokens.map((token, tokenIndex) => (
                      <span key={tokenIndex} className={`token token--${token.type}`}>
                        {token.text}
                      </span>
                    ))}
              </span>
            </div>
          );
        })}
      </pre>
    </section>
  );
}

export default HtmlEditor;
