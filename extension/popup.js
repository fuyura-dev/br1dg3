(function () {
  'use strict';

  /**
   * BR1DG3 — Popup Script
   *
   * Pure UI controller that reads and subscribes to tab state from
   * chrome.storage.local and delegates explicit button clicks to
   * background.js via chrome.runtime.sendMessage.
   */

  const STATUS_STYLES = {
    ON: { text: 'ON', color: 'var(--success-text)' },
    OFF: { text: 'OFF', color: 'var(--text-muted)' },
  };

  function getTabStateKey(tabId) {
    return `tabState_${tabId}`;
  }

  async function getAutoRepairSetting() {
    const { autoRepair } = await chrome.storage.local.get({ autoRepair: false });
    return Boolean(autoRepair);
  }

  async function setAutoRepairSetting(enabled) {
    await chrome.storage.local.set({ autoRepair: Boolean(enabled) });
  }

  async function getTabState(tabId) {
    const key = getTabStateKey(tabId);
    const data = await chrome.storage.local.get(key);
    return data[key] || null;
  }

  async function getActiveTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
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
  let currentTabId = null;

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

  function syncBadgeWithToggle() {
    const isAuto = Boolean(elements.autoRepairToggle && elements.autoRepairToggle.checked);
    setStatusBadge(isAuto ? 'ON' : 'OFF');
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

  function applyTabStateToUi(state) {
    if (!state) return;

    if (state.status === 'scanning') {
      if (elements.rescanBtn) elements.rescanBtn.textContent = 'Scanning...';
      updateStats({ issues: '...', improvements: '...', remaining: '...', result: '...' });
      if (elements.statusMessage) {
        elements.statusMessage.textContent = 'Scanning page...';
      }
      setControlsDisabled(true);
      return;
    }

    if (elements.rescanBtn) elements.rescanBtn.textContent = 'Re-scan Page';

    if (state.status === 'repairing') {
      setStatusText('Repairing...');
      if (elements.repairBtn) elements.repairBtn.textContent = 'Repairing...';
      updateStats({
        issues: state.issues_before ?? '...',
        improvements: '...',
        remaining: '...',
        result: 'Repairing...',
      });
      if (elements.statusMessage) {
        elements.statusMessage.textContent = 'Repairing accessibility issues...';
      }
      setControlsDisabled(true);
      return;
    }

    if (state.status === 'scanned') {
      const totalIssues = state.issues_before ?? 0;
      updateStats({
        issues: totalIssues,
        improvements: 0,
        remaining: totalIssues,
        result: totalIssues > 0 ? 'Needs Repair' : 'Clean',
      });
      canRepair = totalIssues > 0;
      if (elements.repairBtn) {
        elements.repairBtn.disabled = !canRepair;
        elements.repairBtn.textContent = totalIssues === 0 ? 'No Repairs Needed' : 'Repair Page';
      }
      if (elements.summaryContent) {
        elements.summaryContent.textContent =
          state.summary || 'No repair performed yet. Run a repair to see the summary.';
      }
      renderIssuesList(state.issues || []);
      if (elements.statusMessage) {
        elements.statusMessage.textContent =
          totalIssues > 0
            ? `Found ${totalIssues} accessibility issue${totalIssues === 1 ? '' : 's'}. Ready to repair.`
            : 'No accessibility issues found!';
      }
      syncBadgeWithToggle();
      setControlsDisabled(false);
      return;
    }

    if (state.status === 'repaired') {
      const { issues_before = 0, issues_fixed = 0, issues_after = 0, summary = '' } = state;
      updateStats({
        issues: issues_before,
        improvements: issues_fixed,
        remaining: issues_after,
        result:
          issues_after === 0
            ? 'Repaired'
            : issues_fixed > 0
            ? 'Partially Repaired'
            : 'Needs Repair',
      });
      if (elements.summaryContent && summary) {
        elements.summaryContent.textContent = summary;
      }
      canRepair = issues_after > 0;
      if (elements.repairBtn) {
        elements.repairBtn.disabled = !canRepair;
        elements.repairBtn.textContent = issues_after === 0 ? 'Page Repaired' : 'Re-run Repair';
      }
      if (issues_after === 0) {
        renderIssuesList([]);
      } else {
        renderIssuesList(state.issues || []);
      }
      syncBadgeWithToggle();
      if (elements.statusMessage) {
        elements.statusMessage.textContent = `Repair applied: ${issues_fixed} issue${issues_fixed === 1 ? '' : 's'} fixed, ${issues_after} remaining.`;
      }
      setControlsDisabled(false);
      return;
    }

    if (state.status === 'error') {
      showError(state.error || 'Error scanning page. Is the backend running?');
      updateStats({ issues: 'Error', improvements: '--', remaining: '--', result: 'Failed' });
      canRepair = false;
      if (elements.repairBtn) {
        elements.repairBtn.disabled = true;
        elements.repairBtn.textContent = 'Repair Page';
      }
      syncBadgeWithToggle();
      setControlsDisabled(false);
    }
  }

  async function requestScan(forceScan = true) {
    const tab = await getActiveTab();
    if (!tab) return;
    currentTabId = tab.id;

    applyTabStateToUi({ status: 'scanning' });
    const response = await chrome.runtime.sendMessage({
      type: 'SCAN_TAB',
      tabId: tab.id,
      url: tab.url,
      forceScan,
    });
    if (response && response.state) {
      applyTabStateToUi(response.state);
    }
  }

  async function requestRepair(tab) {
    const prev = await getTabState(tab.id);
    applyTabStateToUi({
      status: 'repairing',
      issues_before: prev?.issues_before ?? '...',
    });
    const response = await chrome.runtime.sendMessage({
      type: 'REPAIR_TAB',
      tabId: tab.id,
      url: tab.url,
    });
    if (response && response.state) {
      applyTabStateToUi(response.state);
    }
  }

  async function handleManualRepair() {
    const tab = await getActiveTab();
    if (!tab) return;
    await requestRepair(tab);
  }

  async function disableAutoRepair(tab) {
    setStatusText('Restoring...');
    await chrome.storage.local.remove(getTabStateKey(tab.id));
    await chrome.tabs.reload(tab.id);
    setStatusBadge('OFF');
  }

  async function handleAutoRepairToggle(event) {
    const isEnabled = event.target.checked;
    await setAutoRepairSetting(isEnabled);
    setStatusBadge(isEnabled ? 'ON' : 'OFF');

    try {
      const tab = await getActiveTab();
      if (!tab) return;
      if (isEnabled) {
        const state = await getTabState(tab.id);
        if (!state || (state.status !== 'repaired' && state.status !== 'repairing')) {
          await requestRepair(tab);
        }
      } else {
        await disableAutoRepair(tab);
      }
    } catch (error) {
      console.error('BR1DG3 Repair error:', error);
      showError(error.message || 'Failed to run Repair. Check if the backend is running.');
      event.target.checked = !isEnabled;
      await setAutoRepairSetting(!isEnabled);
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
    if (elements.restoreBtn) {
      elements.restoreBtn.textContent = 'Restoring...';
      elements.restoreBtn.disabled = true;
    }

    try {
      const tab = await getActiveTab();

      await setAutoRepairSetting(false);
      if (elements.autoRepairToggle) {
        elements.autoRepairToggle.checked = false;
      }
      setStatusBadge('OFF');

      await chrome.storage.local.remove(getTabStateKey(tab.id));
      await chrome.tabs.reload(tab.id);

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
    } catch (error) {
      showError('Error restoring webpage.');
    } finally {
      if (elements.restoreBtn) {
        elements.restoreBtn.textContent = 'Restore Original';
        elements.restoreBtn.disabled = false;
      }
    }
  }

  async function initializePopup() {
    const autoRepair = await getAutoRepairSetting();
    if (elements.autoRepairToggle) {
      elements.autoRepairToggle.checked = autoRepair;
    }
    setStatusBadge(autoRepair ? 'ON' : 'OFF');

    const tab = await getActiveTab();
    if (!tab) return;
    currentTabId = tab.id;

    // Live-update UI whenever background.js updates chrome.storage.local
    chrome.storage.onChanged.addListener((changes, areaName) => {
      if (areaName !== 'local') return;
      if (changes.autoRepair && elements.autoRepairToggle) {
        const enabled = Boolean(changes.autoRepair.newValue);
        elements.autoRepairToggle.checked = enabled;
        setStatusBadge(enabled ? 'ON' : 'OFF');
      }
      const tabKey = getTabStateKey(currentTabId);
      if (changes[tabKey] && changes[tabKey].newValue) {
        applyTabStateToUi(changes[tabKey].newValue);
      }
    });

    const existingState = await getTabState(tab.id);

    // If this tab already has a state (scanning, repairing, scanned, repaired, error),
    // simply display it! Never automatically trigger a second scan when opening the popup.
    if (existingState) {
      applyTabStateToUi(existingState);
      return;
    }

    // Only if this tab has no state at all (e.g. opened before extension was installed),
    // ask background.js to check/scan it once.
    await requestScan(false);
  }

  document.addEventListener('DOMContentLoaded', () => {
    elements = queryElements();

    if (elements.repairBtn) {
      elements.repairBtn.addEventListener('click', handleManualRepair);
    }
    if (elements.rescanBtn) {
      elements.rescanBtn.addEventListener('click', () => requestScan(true));
    }
    if (elements.viewSummaryBtn) {
      elements.viewSummaryBtn.addEventListener('click', handleViewSummary);
    }
    if (elements.restoreBtn) {
      elements.restoreBtn.addEventListener('click', handleRestore);
    }
    if (elements.autoRepairToggle) {
      elements.autoRepairToggle.addEventListener('change', handleAutoRepairToggle);
    }

    initializePopup();
  });
})();
