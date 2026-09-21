// Mock data for the Accessibility Repair Studio.
// Aligned with the API's Directed Graph Schema and Axe-core violation outputs.

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

// Aligned with backend API schema: { nodes: [], links: [] }
export const documentGraph = {
  nodes: [
    { id: "html", tag: "html", label: "html", has_issue: false },
    { id: "head", tag: "head", label: "head", has_issue: false },
    { id: "meta", tag: "meta", label: "meta", has_issue: false },
    { id: "title", tag: "title", label: "title", has_issue: false },
    { id: "body", tag: "body", label: "body", has_issue: false },
    { id: "header", tag: "header", label: "header", has_issue: false },
    { id: "h1", tag: "h1", label: "h1", has_issue: false },
    { id: "nav", tag: "nav", label: "nav", has_issue: false },
    { id: "a-home", tag: "a", label: "a", has_issue: false },
    { id: "a-help", tag: "a", label: "a", has_issue: false },
    { id: "content", tag: "div", label: "div.content", has_issue: true, violationId: "V004" },
    { id: "h3", tag: "h3", label: "h3", has_issue: true, violationId: "V003" },
    { id: "form", tag: "form", label: "form#contact-form", has_issue: false },
    { id: "field-name", tag: "div", label: "div.field", has_issue: false },
    { id: "input-name", tag: "input", label: "input#full-name", has_issue: true, violationId: "V001" },
    { id: "field-email", tag: "div", label: "div.field", has_issue: false },
    { id: "label-email", tag: "label", label: "label", has_issue: false },
    { id: "input-email", tag: "input", label: "input#email", has_issue: false },
    { id: "field-message", tag: "div", label: "div.field", has_issue: false },
    { id: "textarea", tag: "textarea", label: "textarea#message", has_issue: false },
    { id: "button", tag: "button", label: "button#submit-button", has_issue: true, violationId: "V002" },
    { id: "svg", tag: "svg", label: "svg", has_issue: false },
    { id: "footer", tag: "footer", label: "footer", has_issue: false },
    { id: "p-copy", tag: "p", label: "p", has_issue: false },
  ],
  links: [
    { source: "html", target: "head", relation: "child" },
    { source: "html", target: "body", relation: "child" },
    { source: "head", target: "meta", relation: "child" },
    { source: "head", target: "title", relation: "child" },
    { source: "body", target: "header", relation: "child" },
    { source: "body", target: "content", relation: "child" },
    { source: "body", target: "footer", relation: "child" },
    { source: "header", target: "h1", relation: "child" },
    { source: "header", target: "nav", relation: "child" },
    { source: "nav", target: "a-home", relation: "child" },
    { source: "nav", target: "a-help", relation: "child" },
    { source: "content", target: "h3", relation: "child" },
    { source: "content", target: "form", relation: "child" },
    { source: "form", target: "field-name", relation: "child" },
    { source: "form", target: "field-email", relation: "child" },
    { source: "form", target: "field-message", relation: "child" },
    { source: "form", target: "button", relation: "child" },
    { source: "field-name", target: "input-name", relation: "child" },
    { source: "field-email", target: "label-email", relation: "child" },
    { source: "field-email", target: "input-email", relation: "child" },
    { source: "field-message", target: "textarea", relation: "child" },
    { source: "button", target: "svg", relation: "child" },
    { source: "footer", target: "p-copy", relation: "child" }
  ]
};

// Aligned with standard Axe-core output schema
export const violations = [
  {
    id: "V001",
    ruleId: "label",
    impact: "critical",
    target: "input#full-name",
    html: "<input type=\"text\" id=\"full-name\" name=\"fullName\" placeholder=\"Full name\" />",
    description: "Text input has no programmatically associated label",
    failureSummary: "Screen reader users hear only 'edit text, blank'; the placeholder is not exposed as a label.",
    status: "applied",
  },
  {
    id: "V002",
    ruleId: "button-name",
    impact: "critical",
    target: "button#submit-button",
    html: "<button type=\"submit\" id=\"submit-button\">...</button>",
    description: "Icon-only submit button has no accessible name",
    failureSummary: "Screen reader users hear only 'button' with no indication of what it submits.",
    status: "applied",
  },
  {
    id: "V003",
    ruleId: "heading-order",
    impact: "moderate",
    target: "h3",
    html: "<h3>Contact form</h3>",
    description: "Heading level skips from h1 to h3",
    failureSummary: "Users navigating by heading level may assume an intervening section is missing.",
    status: "applied",
  },
  {
    id: "V004",
    ruleId: "region",
    impact: "serious",
    target: "div.content",
    html: "<div class=\"content\">...</div>",
    description: "Primary content has no landmark region",
    failureSummary: "Screen reader users cannot jump directly to the main content using landmark navigation.",
    status: "applied",
  },
];

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
    children: [{ tag: "svg", note: "aria-hidden=\"true\"" }],
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
    headingRelationships: [{ status: "gap", note: "Nearest preceding heading is <h1> Customer Support" }],
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

export const repairs = {
  V001: {
    strategy: "Associate an explicit label with the input",
    change: "Added <label for=\"full-name\">Full name</label> immediately before the input, linked via the for/id pair.",
    targetElement: "input#full-name",
    reason: "SDG context showed no existing label anywhere in the form tree, so a new explicit label was introduced rather than reusing one.",
    relatedRelationships: ["parent: div.field", "form: #contact-form"],
    status: "applied",
  },
  V002: {
    strategy: "Add an accessible name via aria-label",
    change: "Added aria-label=\"Submit contact form\" to the button.",
    targetElement: "button#submit-button",
    reason: "The SVG child is intentionally aria-hidden for decoration, so the accessible name has to come from the button itself.",
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
    reason: "DOM hierarchy showed header and footer landmarks already existed, but the content between them had no landmark role.",
    relatedRelationships: ["sibling: header", "sibling: footer"],
    status: "applied",
  },
};

export const evaluationMetrics = [
  { id: "effectiveness", label: "Repair Effectiveness", score: 96, detail: "4 of 4 detected violations fully resolved" },
  { id: "safety", label: "Repair Safety", score: 98, detail: "No structural or functional side effects introduced" },
  { id: "structural", label: "Structural Preservation", score: 94, detail: "36 of 38 DOM nodes preserved without alteration" },
  { id: "efficiency", label: "Repair Efficiency", score: 91, detail: "4 of 4 repairs completed in a single generation pass" },
  { id: "semantic", label: "Semantic Dependency Preservation", score: 93, detail: "13 of 14 SDG relationships preserved after repair" },
];