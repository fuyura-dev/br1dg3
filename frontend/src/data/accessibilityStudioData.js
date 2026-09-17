// Mock data for the Accessibility Repair Studio.
//
// This file plays the role the future BR1DG3 backend/LLM pipeline will
// play once connected: it is the single source of the workspace's HTML
// documents, detected violations, SDG relationship graphs (both the
// per-violation context and the full document graph), generated repairs,
// and evaluation scores. Every component reads this shape only through
// `services/accessibilityRepairService.js`, so replacing this file with
// real API responses later requires no component changes.

export const htmlSource = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Contact Support</title>
  </head>
  <body>
    <header>
      <h1>Customer Support</h1>
      <nav>
        <a href="/">Home</a>
        <a href="/help">Help Center</a>
      </nav>
    </header>

    <div class="content">
      <h3>Contact form</h3>
      <form id="contact-form">
        <div class="field">
          <input type="text" id="full-name" name="fullName" placeholder="Full name" />
        </div>
        <div class="field">
          <label>Email address</label>
          <input type="email" id="email" name="email" />
        </div>
        <div class="field">
          <textarea id="message" name="message" placeholder="How can we help?"></textarea>
        </div>
        <button type="submit" id="submit-button">
          <svg aria-hidden="true" width="16" height="16"><path d="M2 2l12 6-12 6z"/></svg>
        </button>
      </form>
    </div>

    <footer>
      <p>&copy; 2026 BR1DG3 Support</p>
    </footer>
  </body>
</html>`;

export const repairedHtml = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Contact Support</title>
  </head>
  <body>
    <header>
      <h1>Customer Support</h1>
      <nav>
        <a href="/">Home</a>
        <a href="/help">Help Center</a>
      </nav>
    </header>

    <main id="main-content">
      <h2>Contact form</h2>
      <form id="contact-form">
        <div class="field">
          <label for="full-name">Full name</label>
          <input type="text" id="full-name" name="fullName" placeholder="Full name" />
        </div>
        <div class="field">
          <label for="email">Email address</label>
          <input type="email" id="email" name="email" />
        </div>
        <div class="field">
          <textarea id="message" name="message" placeholder="How can we help?"></textarea>
        </div>
        <button type="submit" id="submit-button" aria-label="Submit contact form">
          <svg aria-hidden="true" width="16" height="16"><path d="M2 2l12 6-12 6z"/></svg>
        </button>
      </form>
    </main>

    <footer>
      <p>&copy; 2026 BR1DG3 Support</p>
    </footer>
  </body>
</html>`;

// Flat representation of the whole document's DOM hierarchy, used by the
// SDG graph visualizer's "Full document" view. Each node names its parent
// by id; nodes tied to a detected violation carry violationId so the
// visualizer can highlight them. This mirrors `htmlSource` above, not
// `repairedHtml` -- the graph shows the structure the violations were
// detected against.
export const documentGraph = {
  rootId: "html",
  nodes: [
    { id: "html", label: "html" },
    { id: "head", label: "head", parent: "html" },
    { id: "meta", label: "meta", parent: "head" },
    { id: "title", label: "title", parent: "head" },
    { id: "body", label: "body", parent: "html" },
    { id: "header", label: "header", parent: "body" },
    { id: "h1", label: "h1", parent: "header" },
    { id: "nav", label: "nav", parent: "header" },
    { id: "a-home", label: "a", parent: "nav" },
    { id: "a-help", label: "a", parent: "nav" },
    { id: "content", label: "div.content", parent: "body", violationId: "V004" },
    { id: "h3", label: "h3", parent: "content", violationId: "V003" },
    { id: "form", label: "form#contact-form", parent: "content" },
    { id: "field-name", label: "div.field", parent: "form" },
    { id: "input-name", label: "input#full-name", parent: "field-name", violationId: "V001" },
    { id: "field-email", label: "div.field", parent: "form" },
    { id: "label-email", label: "label", parent: "field-email" },
    { id: "input-email", label: "input#email", parent: "field-email" },
    { id: "field-message", label: "div.field", parent: "form" },
    { id: "textarea", label: "textarea#message", parent: "field-message" },
    { id: "button", label: "button#submit-button", parent: "form", violationId: "V002" },
    { id: "svg", label: "svg", parent: "button" },
    { id: "footer", label: "footer", parent: "body" },
    { id: "p-copy", label: "p", parent: "footer" },
  ],
};

export const violations = [
  {
    id: "V001",
    severity: "critical",
    wcag: "1.3.1",
    element: "input#full-name",
    description: "Text input has no programmatically associated label",
    screenReaderImpact:
      "Screen reader users hear only \u201cedit text, blank\u201d; the placeholder is not exposed as a label.",
    line: 20,
    status: "applied",
  },
  {
    id: "V002",
    severity: "critical",
    wcag: "4.1.2",
    element: "button#submit-button",
    description: "Icon-only submit button has no accessible name",
    screenReaderImpact:
      "Screen reader users hear only \u201cbutton\u201d with no indication of what it submits.",
    line: 29,
    status: "applied",
  },
  {
    id: "V003",
    severity: "moderate",
    wcag: "1.3.1",
    element: "h3 (Contact form)",
    description: "Heading level skips from h1 to h3",
    screenReaderImpact:
      "Users navigating by heading level may assume an intervening section is missing.",
    line: 17,
    status: "applied",
  },
  {
    id: "V004",
    severity: "serious",
    wcag: "2.4.1",
    element: "div.content",
    description: "Primary content has no landmark region",
    screenReaderImpact:
      "Screen reader users cannot jump directly to the main content using landmark navigation.",
    line: 16,
    status: "applied",
  },
];

// Structural Dependency Graph context for each violation, keyed by
// violation id. Shapes are intentionally uniform across relationship
// types so a single component can render any of them.
export const sdgGraph = {
  V001: {
    target: { tag: "input", id: "full-name", classes: [] },
    parent: { tag: "div", classes: ["field"] },
    children: [],
    siblings: [{ tag: "div", classes: ["field"], note: "Adjacent field wraps the email input" }],
    labelRelationships: [{ status: "missing", note: "No <label for=\"full-name\"> exists in the document" }],
    headingRelationships: [],
    formRelationships: [{ tag: "form", id: "contact-form", note: "Input is a required field of the contact form" }],
    domPath: ["html", "body", "div.content", "form#contact-form", "div.field", "input#full-name"],
  },
  V002: {
    target: { tag: "button", id: "submit-button", classes: [] },
    parent: { tag: "form", id: "contact-form" },
    children: [{ tag: "svg", note: "aria-hidden=\"true\" \u2014 removed from the accessibility tree" }],
    labelRelationships: [{ status: "missing", note: "No aria-label, aria-labelledby, or visible text content" }],
    headingRelationships: [],
    formRelationships: [{ tag: "form", id: "contact-form", note: "Button is the form's only submit control" }],
    domPath: ["html", "body", "div.content", "form#contact-form", "button#submit-button", "svg"],
  },
  V003: {
    target: { tag: "h3", classes: [] },
    parent: { tag: "div", classes: ["content"] },
    children: [],
    siblings: [{ tag: "form", id: "contact-form", note: "Follows immediately after the heading" }],
    labelRelationships: [],
    headingRelationships: [{ status: "gap", note: "Nearest preceding heading is <h1> Customer Support \u2014 no <h2> exists between them" }],
    formRelationships: [],
    domPath: ["html", "body", "div.content", "h3"],
  },
  V004: {
    target: { tag: "div", classes: ["content"] },
    parent: { tag: "body", classes: [] },
    children: [
      { tag: "h3", note: "Section heading" },
      { tag: "form", id: "contact-form", note: "Primary interactive content" },
    ],
    siblings: [
      { tag: "header", note: "Already an implicit banner landmark" },
      { tag: "footer", note: "Already an implicit contentinfo landmark" },
    ],
    labelRelationships: [],
    headingRelationships: [],
    formRelationships: [],
    domPath: ["html", "body", "div.content"],
  },
};

// Generated repairs, keyed by violation id.
export const repairs = {
  V001: {
    strategy: "Associate an explicit label with the input",
    change:
      "Added <label for=\"full-name\">Full name</label> immediately before the input, linked via the for/id pair.",
    targetElement: "input#full-name",
    reason:
      "SDG context showed no existing label anywhere in the form tree, so a new explicit label was introduced rather than reusing one.",
    relatedRelationships: ["parent: div.field", "form: #contact-form"],
    status: "applied",
  },
  V002: {
    strategy: "Add an accessible name via aria-label",
    change: "Added aria-label=\"Submit contact form\" to the button.",
    targetElement: "button#submit-button",
    reason:
      "The SVG child is intentionally aria-hidden for decoration, so the accessible name has to come from the button itself.",
    relatedRelationships: ["child: svg[aria-hidden]", "form: #contact-form"],
    status: "applied",
  },
  V003: {
    strategy: "Normalize the heading level",
    change: "Changed <h3>Contact form</h3> to <h2>Contact form</h2>.",
    targetElement: "h3 (Contact form)",
    reason: "Heading relationship data showed the nearest ancestor heading was h1 with no h2 in between.",
    relatedRelationships: ["heading: h1 Customer Support"],
    status: "applied",
  },
  V004: {
    strategy: "Wrap primary content in a landmark",
    change: "Replaced div.content with <main id=\"main-content\">.",
    targetElement: "div.content",
    reason:
      "DOM hierarchy showed header and footer landmarks already existed, but the content between them had no landmark role.",
    relatedRelationships: ["sibling: header", "sibling: footer"],
    status: "applied",
  },
};

export const evaluationMetrics = [
  {
    id: "effectiveness",
    label: "Repair Effectiveness",
    score: 96,
    detail: "4 of 4 detected violations fully resolved",
  },
  {
    id: "safety",
    label: "Repair Safety",
    score: 98,
    detail: "No structural or functional side effects introduced",
  },
  {
    id: "structural",
    label: "Structural Preservation",
    score: 94,
    detail: "36 of 38 DOM nodes preserved without alteration",
  },
  {
    id: "efficiency",
    label: "Repair Efficiency",
    score: 91,
    detail: "4 of 4 repairs completed in a single generation pass",
  },
  {
    id: "semantic",
    label: "Semantic Dependency Preservation",
    score: 93,
    detail: "13 of 14 SDG relationships preserved after repair",
  },
];
