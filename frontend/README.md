# BR1DG3 Frontend

Vite + React application for the BR1DG3 project, including the **Accessibility
Repair Studio** analytical dashboard.

## Getting started

```bash
npm install
npm run dev
```

Build for production:

```bash
npm run build
npm run preview
```

## Accessibility Repair Studio

Located under `src/components/accessibility-studio/`. It is a researcher-facing
workspace for inspecting the repair pipeline: uploaded HTML, detected
violations, the Structural Dependency Graph (SDG) context behind each
violation, the generated repair, a side-by-side diff against the repaired
document, and the study's five evaluation metrics (Repair Effectiveness,
Repair Safety, Structural Preservation, Repair Efficiency, and Semantic
Dependency Preservation).

### Architecture

```
src/
├── components/accessibility-studio/   UI only — renders props, no data or business logic
├── data/accessibilityStudioData.js    Mock documents, violations, SDG graphs, repairs, metrics
├── services/accessibilityRepairService.js  Async data-access boundary (swap for a real API later)
├── hooks/useAccessibilityStudio.js    Dashboard state: selection, loading, derived data
└── utils/                             Pure helpers: severity/status lookup, formatting, diffing, tokenizing
```

Selecting a violation in the workspace updates the highlighted line in the
HTML editor, the SDG context panel, and the generated repair panel, all
driven from `useAccessibilityStudio`.

### SDG graph visualizer

The "View SDG Graph" button in the SDG Context panel opens a modal
(`SdgGraphModal.jsx`) with two views, toggled in place:

- **Selected violation** — a hub-and-spoke diagram centered on the
  violation's target element, with its parent/children/siblings and
  label/heading/form relationships as satellites.
- **Full document** — a top-down tree of the entire document's DOM
  hierarchy (`data/accessibilityStudioData.js`'s `documentGraph`), with
  violation-linked nodes outlined; clicking one selects that violation and
  jumps back to the local view.

Layout math (tree positions and radial satellite placement) lives in
`utils/graphLayout.js` as plain functions with no rendering concerns, and
the SVG itself is hand-drawn with no charting/graph library dependency.

### Connecting a real backend

Every method in `accessibilityRepairService.js` is already async and keyed
the way a REST/LLM API would be (`getWorkspace()`, `getSdgContext(id)`,
`getRepair(id)`). Swapping the mock data in `data/accessibilityStudioData.js`
for real `fetch()` calls inside that service is the only change needed —
no component or hook code depends on the data being local.
