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
      repairBtn: document.getElementById('repair-btn'),
      rescanBtn: document.getElementById('rescan-btn'),
      viewSummaryBtn: document.getElementById('view-summary-btn'),
      restoreBtn: document.getElementById('restore-btn'),
      statIssues: document.getElementById('stat-issues'),
      statImprovements: document.getElementById('stat-improvements'),
      statRemaining: document.getElementById('stat-remaining') || document.getElementById('stat-structure'),
      statResult: document.getElementById('stat-result'),
      summaryBox: document.getElementById('summary-box'),
      summaryContent: document.getElementById('summary-content'),
      issuesList: document.getElementById('issues-list'),
      issuesListSection: document.getElementById('issues-list-section'),
    };
  }

  let elements;
  let canRepair = false;

  function updateStats(partial) {
    if ('issues' in partial && elements.statIssues) elements.statIssues.textContent = partial.issues;
    if ('improvements' in partial && elements.statImprovements) elements.statImprovements.textContent = partial.improvements;
    if ('remaining' in partial && elements.statRemaining) elements.statRemaining.textContent = partial.remaining;
    if ('structure' in partial && elements.statRemaining) elements.statRemaining.textContent = partial.structure;
    if ('result' in partial && elements.statResult) elements.statResult.textContent = partial.result;
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
    if (!button) return () => {};
    const originalLabel = button.textContent;
    button.textContent = loadingLabel;
    button.disabled = true;
    return () => {
      button.textContent = originalLabel;
      button.disabled = false;
    };
  }

  function setControlsDisabled(disabled) {
    if (disabled) {
      if (elements.repairBtn) elements.repairBtn.disabled = true;
      if (elements.rescanBtn) elements.rescanBtn.disabled = true;
      if (elements.viewSummaryBtn) elements.viewSummaryBtn.disabled = true;
      if (elements.restoreBtn) elements.restoreBtn.disabled = true;
      if (elements.autoRepairToggle) elements.autoRepairToggle.disabled = true;
    } else {
      if (elements.repairBtn) elements.repairBtn.disabled = !canRepair;
      if (elements.rescanBtn) elements.rescanBtn.disabled = false;
      if (elements.viewSummaryBtn) elements.viewSummaryBtn.disabled = false;
      if (elements.restoreBtn) elements.restoreBtn.disabled = false;
      if (elements.autoRepairToggle) elements.autoRepairToggle.disabled = false;
    }
  }

  function renderIssuesList(issues) {
    if (!elements.issuesList || !elements.issuesListSection) return;

    elements.issuesList.innerHTML = '';
    if (!issues || issues.length === 0) {
      elements.issuesListSection.style.display = 'none';
      return;
    }

    elements.issuesListSection.style.display = 'block';

    const issueMap = new Map();
    for (const issue of issues) {
      const key = issue.id || 'unknown';
      if (!issueMap.has(key)) {
        issueMap.set(key, {
          id: issue.id,
          impact: issue.impact || 'minor',
          help: issue.help || issue.description || issue.id,
          count: 1,
        });
      } else {
        issueMap.get(key).count += 1;
      }
    }

    for (const item of issueMap.values()) {
      const li = document.createElement('li');
      li.className = 'issue-item';

      const label = document.createElement('span');
      label.className = 'issue-label';
      label.textContent = `${item.help} (${item.count})`;
      label.title = item.help;

      const badge = document.createElement('span');
      badge.className = `issue-badge ${item.impact.toLowerCase()}`;
      badge.textContent = item.impact;

      li.appendChild(label);
      li.appendChild(badge);
      elements.issuesList.appendChild(li);
    }
  }

  // ---------------------------------------------------------------------
  // Feature handlers — one function per user action, each owning its own
  // try/catch/finally so a failure in one can't leave another mid-state.
  // ---------------------------------------------------------------------

  async function handleScan() {
    const restoreButton = withButtonLoading(elements.rescanBtn, 'Scanning...');
    updateStats({ issues: '...', improvements: '...', remaining: '...', result: '...' });

    try {
      const tab = await getActiveTab();
      const html = await getTabHtml(tab.id);
      const { total_issues, issues } = await api.scan(html);

      updateStats({
        issues: total_issues,
        improvements: 0,
        remaining: total_issues,
        result: total_issues > 0 ? 'Needs Repair' : 'Clean',
      });

      canRepair = total_issues > 0;
      if (elements.repairBtn) {
        elements.repairBtn.disabled = !canRepair;
        elements.repairBtn.textContent = total_issues === 0 ? 'No Repairs Needed' : 'Repair Page';
      }

      renderIssuesList(issues);

      if (elements.statusMessage) {
        elements.statusMessage.textContent = total_issues > 0
          ? `Found ${total_issues} accessibility issue${total_issues === 1 ? '' : 's'}. Ready to repair.`
          : 'No accessibility issues found!';
      }

      if (elements.autoRepairToggle && elements.autoRepairToggle.checked && total_issues > 0) {
        await executeRepair(tab);
      }

    } catch (error) {
      console.error('BR1DG3 Scan error:', error);
      showError(error.message || 'Error scanning page. Is the backend running?');
      updateStats({ issues: 'Error', improvements: '--', remaining: '--', result: 'Failed' });
      canRepair = false;
      if (elements.repairBtn) {
        elements.repairBtn.disabled = true;
        elements.repairBtn.textContent = 'Repair Page';
      }
      if (elements.statusMessage) {
        elements.statusMessage.textContent = error.message || 'Scan failed. Check if backend is running.';
      }
    } finally {
      restoreButton();
    }
  }

  async function executeRepair(tab) {
    console.log('[BR1DG3] Executing repair on tab:', tab.id);
    setStatusText('Repairing...');
    if (elements.statusMessage) {
      elements.statusMessage.textContent = 'Repairing accessibility issues...';
    }

    const html = await getTabHtml(tab.id);
    console.log('[BR1DG3] Calling POST /api/repair (HTML length:', html ? html.length : 0, ')...');
    const { fixed_html, issues_before, issues_fixed, issues_after, summary } = await api.repair(html);
    console.log('[BR1DG3] Repair response:', { issues_before, issues_fixed, issues_after, summary });

    await injectHtml(tab.id, fixed_html);
    console.log('[BR1DG3] Injected repaired HTML into tab DOM.');

    updateStats({
      issues: issues_before,
      improvements: issues_fixed,
      remaining: issues_after,
      result: issues_after === 0 ? 'Repaired' : (issues_fixed > 0 ? 'Partially Repaired' : 'Needs Repair'),
    });

    if (elements.summaryContent) {
      elements.summaryContent.textContent = summary;
    }

    canRepair = issues_after > 0;
    if (elements.repairBtn) {
      elements.repairBtn.disabled = !canRepair;
      elements.repairBtn.textContent = issues_after === 0 ? 'Page Repaired' : 'Re-run Repair';
    }

    if (issues_after === 0 && elements.issuesListSection) {
      elements.issuesListSection.style.display = 'none';
    }

    setStatusBadge('ON');

    if (elements.statusMessage) {
      elements.statusMessage.textContent = `Repair applied: ${issues_fixed} issue${issues_fixed === 1 ? '' : 's'} fixed, ${issues_after} remaining.`;
    }
  }

  async function handleManualRepair() {
    if (!elements.repairBtn) return;
    console.log('[BR1DG3] Repair button clicked.');
    const originalLabel = elements.repairBtn.textContent;
    elements.repairBtn.textContent = 'Repairing...';
    elements.repairBtn.disabled = true;

    try {
      const tab = await getActiveTab();
      await executeRepair(tab);
    } catch (error) {
      console.error('[BR1DG3] Repair error:', error);
      showError(error.message || 'Failed to run repair.');
      if (elements.statusMessage) {
        elements.statusMessage.textContent = error.message || 'Repair failed.';
      }
      elements.repairBtn.textContent = originalLabel;
      elements.repairBtn.disabled = false;
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
        await executeRepair(tab);
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

      if (elements.autoRepairToggle) {
        elements.autoRepairToggle.checked = false;
      }
      setStatusBadge('OFF');

      if (elements.statusMessage) {
        elements.statusMessage.textContent = 'Page restored to original.';
      }

      if (elements.summaryContent) {
        elements.summaryContent.textContent = 'No repair performed yet. Run a repair to see the summary.';
      }
      renderIssuesList([]);
      canRepair = false;
      if (elements.repairBtn) {
        elements.repairBtn.disabled = true;
        elements.repairBtn.textContent = 'Repair Page';
      }

      setTimeout(() => {
        withExclusiveLock(handleScan);
      }, 600);
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

    if (elements.repairBtn) {
      elements.repairBtn.addEventListener('click', () => withExclusiveLock(handleManualRepair));
    }
    if (elements.rescanBtn) {
      elements.rescanBtn.addEventListener('click', () => withExclusiveLock(handleScan));
    }
    if (elements.viewSummaryBtn) {
      elements.viewSummaryBtn.addEventListener('click', handleViewSummary);
    }
    if (elements.restoreBtn) {
      elements.restoreBtn.addEventListener('click', () => withExclusiveLock(handleRestore));
    }
    if (elements.autoRepairToggle) {
      elements.autoRepairToggle.addEventListener('change', (event) =>
        withExclusiveLock(() => handleAutoRepairToggle(event))
      );
    }

    withExclusiveLock(handleScan); // run a scan as soon as the popup opens
  });
})();
