(function () {
  'use strict';

  /**
   * BR1DG3 — Popup Script
   *
   * Wires up the extension popup UI to the local FastAPI backend that scans,
   * repairs, and graphs the accessibility structure of the active tab.
   * Backend contract: POST /api/scan, POST /api/repair, POST /api/graph.
   */

  // ---------------------------------------------------------------------
  // Config
  // ---------------------------------------------------------------------

  const CONFIG = {
    API_BASE_URL: 'http://127.0.0.1:8000/api',
    ENDPOINTS: {
      SCAN: '/scan',
      REPAIR: '/repair',
      GRAPH: '/graph',
    },
  };

  const STATUS_STYLES = {
    ON: { text: 'ON', color: 'var(--success-text)' },
    OFF: { text: 'OFF', color: 'var(--text-muted)' },
  };

  // ---------------------------------------------------------------------
  // API layer — the only place that knows about fetch(), headers, and
  // error shapes. Everything else just calls api.scan/repair/graph().
  // ---------------------------------------------------------------------

  class ApiError extends Error {
    constructor(message, status = 0) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  }

  async function postJson(endpoint, payload) {
    let response;
    try {
      response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch (networkError) {
      throw new ApiError('Could not reach the backend. Is it running?');
    }

    if (!response.ok) {
      let detail = '';
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
          detail = `: ${errorData.detail}`;
        }
      } catch (_) {}
      throw new ApiError(`Backend returned ${response.status}${detail}`, response.status);
    }

    return response.json();
  }

  const api = {
    scan: (html) => postJson(CONFIG.ENDPOINTS.SCAN, { html }),
    repair: (html) => postJson(CONFIG.ENDPOINTS.REPAIR, { html, use_sdg: true }),
    graph: (html) => postJson(CONFIG.ENDPOINTS.GRAPH, { html }),
  };

  // ---------------------------------------------------------------------
  // Chrome tab helpers
  // ---------------------------------------------------------------------

  async function getActiveTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  async function getTabHtml(tabId) {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => document.documentElement.outerHTML,
    });
    return result;
  }

  async function injectHtml(tabId, html) {
    // document.write() fully re-parses the page — that's intentional, it's
    // how the repaired HTML replaces the live DOM. Any in-page JS state is
    // lost in the process, which is expected for a repair pass.
    await chrome.scripting.executeScript({
      target: { tabId },
      func: (newHtml) => {
        document.open();
        document.write(newHtml);
        document.close();
      },
      args: [html],
    });
  }

  // ---------------------------------------------------------------------
  // DOM wiring
  // ---------------------------------------------------------------------

  // The old version picked buttons positionally
  // (`document.querySelectorAll('.btn-primary')[0]`), which silently
  // breaks the moment a button is added, removed, or reordered in
  // popup.html. This resolves by id, with a console-warned fallback so
  // nothing breaks today even before popup.html is updated with ids.
  function resolveButton(id, fallbackSelector, fallbackIndex) {
    const byId = document.getElementById(id);
    if (byId) return byId;
    console.warn(
      `#${id} not found in popup.html — using "${fallbackSelector}"[${fallbackIndex}] instead. ` +
      `Add id="${id}" to that button to remove this warning and this fallback.`
    );
    return document.querySelectorAll(fallbackSelector)[fallbackIndex] ?? null;
  }

  function queryElements() {
    return {
      autoRepairToggle: document.querySelector('.switch input'),
      statusBadge: document.querySelector('.status-badge'),
      statusMessage: document.getElementById('status-message'),
      rescanBtn: document.getElementById('rescan-btn'),
      viewSummaryBtn: document.getElementById('view-summary-btn'),
      restoreBtn: document.getElementById('restore-btn'),
      statIssues: document.getElementById('stat-issues'),
      statImprovements: document.getElementById('stat-improvements'),
      statStructure: document.getElementById('stat-structure'),
      statResult: document.getElementById('stat-result'),
    };
  }

  let elements;

  function updateStats(partial) {
    if ('issues' in partial) elements.statIssues.textContent = partial.issues;
    if ('improvements' in partial) elements.statImprovements.textContent = partial.improvements;
    if ('structure' in partial) elements.statStructure.textContent = partial.structure;
    if ('result' in partial) elements.statResult.textContent = partial.result;
  }

  function setStatusBadge(state) {
    const { text, color } = STATUS_STYLES[state];
    elements.statusBadge.textContent = text;
    elements.statusBadge.style.color = color;
    elements.statusBadge.style.borderColor = color;
    if (state === 'OFF') {
      elements.statusBadge.classList.add('off');
    } else {
      elements.statusBadge.classList.remove('off');
    }
  }

  function setStatusText(text) {
    elements.statusBadge.textContent = text;
  }

  function showError(message) {
    console.error(message);
    if (elements && elements.statusMessage) {
      elements.statusMessage.textContent = message;
    }
  }

  function withButtonLoading(button, loadingLabel) {
    const originalLabel = button.textContent;
    button.textContent = loadingLabel;
    button.disabled = true;
    return () => {
      button.textContent = originalLabel;
      button.disabled = false;
    };
  }

  function setControlsDisabled(disabled) {
    elements.rescanBtn.disabled = disabled;
    elements.viewSummaryBtn.disabled = disabled;
    elements.restoreBtn.disabled = disabled;
    elements.autoRepairToggle.disabled = disabled;
  }

  // ---------------------------------------------------------------------
  // Feature handlers — one function per user action, each owning its own
  // try/catch/finally so a failure in one can't leave another mid-state.
  // ---------------------------------------------------------------------

  async function handleScan() {
    const restoreButton = withButtonLoading(elements.rescanBtn, 'Scanning...');
    updateStats({ issues: '...', improvements: '...', structure: '...', result: '...' });

    try {
      const tab = await getActiveTab();
      const html = await getTabHtml(tab.id);
      const { total_issues } = await api.scan(html);

      updateStats({
        issues: total_issues,
        improvements: 0,
        structure: 1,
        result: total_issues > 0 ? 'Needs Repair' : 'Clean',
      });

      if (elements.statusMessage) {
        elements.statusMessage.textContent = total_issues > 0
          ? `Found ${total_issues} accessibility issue${total_issues === 1 ? '' : 's'}.`
          : 'No accessibility issues found!';
      }

    } catch (error) {
      console.error('BR1DG3 Scan error:', error);
      showError(error.message || 'Error scanning page. Is the backend running?');
      updateStats({ issues: 'Error', improvements: '--', structure: '--', result: 'Failed' });
      if (elements.statusMessage) {
        elements.statusMessage.textContent = error.message || 'Scan failed. Check if backend is running.';
      }
    } finally {
      restoreButton();
    }

  }

  async function enableAutoRepair(tab) {
    setStatusText('Repairing...');
    if (elements.statusMessage) {
      elements.statusMessage.textContent = 'Repairing accessibility issues...';
    }

    const html = await getTabHtml(tab.id);
    const { fixed_html, issues_fixed, issues_after, summary } = await api.repair(html);
    await injectHtml(tab.id, fixed_html);

    updateStats({ issues: issues_after, improvements: issues_fixed, result: 'Repaired' });

    // Store summary in the box
    const summaryContent = document.getElementById('summary-content');
    if (summaryContent) {
      summaryContent.textContent = summary;
    }
    setStatusBadge('ON');

    if (elements.statusMessage) {
      elements.statusMessage.textContent = `Repair applied: ${issues_fixed} issue${issues_fixed === 1 ? '' : 's'} fixed.`;
    }
  }

  async function disableAutoRepair(tab) {
    setStatusText('Restoring...');
    await chrome.tabs.reload(tab.id);
    setStatusBadge('OFF');
  }

  async function handleAutoRepairToggle(event) {
    const isEnabled = event.target.checked;

    try {
      const tab = await getActiveTab();
      if (isEnabled) {
        await enableAutoRepair(tab);
      } else {
        await disableAutoRepair(tab);
      }
    } catch (error) {
      console.error('BR1DG3 Repair error:', error);
      showError(error.message || 'Failed to run Repair. Check if the backend is running.');
      if (elements.statusMessage) {
        elements.statusMessage.textContent = error.message || 'Repair failed.';
      }
      event.target.checked = !isEnabled;
      setStatusBadge(!isEnabled ? 'ON' : 'OFF');
    }
  }

  function handleViewSummary() {
    const box = document.getElementById('summary-box');
    if (!box) return;

    const isHidden = box.style.display === 'none';
    box.style.display = isHidden ? 'block' : 'none';
    elements.viewSummaryBtn.textContent = isHidden ? 'Hide Summary' : 'View Summary';
  }

  async function handleRestore() {
    const restoreButton = withButtonLoading(elements.restoreBtn, 'Restoring...');

    try {
      const tab = await getActiveTab();
      await chrome.tabs.reload(tab.id);

      elements.autoRepairToggle.checked = false;
      setStatusBadge('OFF');

      if (elements.statusMessage) {
        elements.statusMessage.textContent = 'Page restored to original.';
      }

      alert('Webpage restored to original state!');
    } catch (error) {
      showError('Error restoring webpage.');
    } finally {
      restoreButton();
    }
  }

  // ---------------------------------------------------------------------
  // Init — a single busy-lock stops overlapping requests (e.g. clicking
  // "Restore" while a scan is still in flight) from racing each other.
  // ---------------------------------------------------------------------

  let isBusy = false;

  async function withExclusiveLock(action) {
    if (isBusy) return;
    isBusy = true;
    setControlsDisabled(true);
    try {
      await action();
    } finally {
      isBusy = false;
      setControlsDisabled(false);
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    elements = queryElements();

    elements.rescanBtn.addEventListener('click', () => withExclusiveLock(handleScan));
    elements.viewSummaryBtn.addEventListener('click', () => withExclusiveLock(handleViewSummary));
    elements.restoreBtn.addEventListener('click', () => withExclusiveLock(handleRestore));
    elements.autoRepairToggle.addEventListener('change', (event) =>
      withExclusiveLock(() => handleAutoRepairToggle(event))
    );

    withExclusiveLock(handleScan); // run a scan as soon as the popup opens
  });
})();
