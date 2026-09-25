const CONFIG = {
  API_BASE_URL: 'http://127.0.0.1:8000/api',
  ENDPOINTS: {
    SCAN: '/scan',
    REPAIR: '/repair',
  },
};

function isScannableUrl(url) {
  if (!url) return false;
  return (
    url.startsWith('http://') ||
    url.startsWith('https://') ||
    url.startsWith('file://')
  );
}

function getTabStateKey(tabId) {
  return `tabState_${tabId}`;
}

async function getTabState(tabId) {
  const key = getTabStateKey(tabId);
  const data = await chrome.storage.local.get(key);
  return data[key] || null;
}

async function setTabState(tabId, state) {
  const nextState = {
    ...state,
    updatedAt: Date.now(),
  };
  await chrome.storage.local.set({
    [getTabStateKey(tabId)]: nextState,
  });
  return nextState;
}

// Keep the service worker awake while waiting for long LLM responses
function startKeepAlive() {
  const timer = setInterval(() => {
    chrome.runtime.getPlatformInfo(() => {});
  }, 15000);
  return () => clearInterval(timer);
}

async function postJson(endpoint, payload) {
  const stopKeepAlive = startKeepAlive();
  let response;
  try {
    response = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (_) {
    stopKeepAlive();
    throw new Error('Could not reach the backend. Is it running?');
  }

  try {
    if (!response.ok) {
      let detail = '';
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
          detail = `: ${errorData.detail}`;
        }
      } catch (_) {}
      throw new Error(`Backend returned ${response.status}${detail}`);
    }

    return await response.json();
  } finally {
    stopKeepAlive();
  }
}

async function getTabHtml(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => (document.documentElement ? document.documentElement.outerHTML : ''),
  });
  return result || '';
}

async function injectRepairedHtml(tabId, html) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (newHtml) => {
      const parser = new DOMParser();
      const newDoc = parser.parseFromString(newHtml, 'text/html');

      if (newDoc.documentElement && document.documentElement) {
        for (const attr of Array.from(newDoc.documentElement.attributes)) {
          document.documentElement.setAttribute(attr.name, attr.value);
        }
      }

      if (newDoc.title && document.title !== newDoc.title) {
        document.title = newDoc.title;
      }

      if (newDoc.body && document.body) {
        for (const attr of Array.from(newDoc.body.attributes)) {
          document.body.setAttribute(attr.name, attr.value);
        }
        document.body.innerHTML = newDoc.body.innerHTML;
      }

      return document.documentElement ? document.documentElement.outerHTML : '';
    },
    args: [html],
  });
  return result || html;
}

async function executeRepairInternal(tabId, tabUrl, originalHtml, existingIssues = []) {
  const prev = await getTabState(tabId);
  await setTabState(tabId, {
    url: tabUrl,
    status: 'repairing',
    originalHtml,
    repairedHtml: prev?.repairedHtml || null,
    issues_before: prev?.issues_before ?? '...',
    issues_fixed: 0,
    issues_after: prev?.issues_after ?? '...',
    issues: existingIssues,
    summary: 'Repairing accessibility issues...',
  });

  const {
    fixed_html,
    issues_before,
    issues_fixed,
    issues_after,
    summary,
  } = await postJson(CONFIG.ENDPOINTS.REPAIR, {
    html: originalHtml,
    use_sdg: true,
  });

  // Inject into the live DOM and capture the resulting outerHTML as repairedHtml
  const liveRepairedHtml = await injectRepairedHtml(tabId, fixed_html);

  const repairedState = await setTabState(tabId, {
    url: tabUrl,
    status: 'repaired',
    originalHtml,
    repairedHtml: liveRepairedHtml,
    issues_before,
    issues_fixed,
    issues_after,
    issues: issues_after === 0 ? [] : existingIssues || [],
    summary,
  });

  return repairedState;
}

async function runScanAndMaybeRepair(tabId, tabUrl, { forceScan = false } = {}) {
  if (!isScannableUrl(tabUrl)) return null;

  const existingState = await getTabState(tabId);

  // 1. Track ongoing scan/repair: never start another if one is already in progress
  if (
    existingState &&
    (existingState.status === 'scanning' || existingState.status === 'repairing')
  ) {
    return existingState;
  }

  let currentHtml = '';
  try {
    currentHtml = await getTabHtml(tabId);
  } catch (_) {
    return null;
  }
  if (!currentHtml) return null;

  // 2. Avoid scanning/repairing again if current HTML equals originalHtml or repairedHtml
  if (
    !forceScan &&
    existingState &&
    (currentHtml === existingState.originalHtml ||
      currentHtml === existingState.repairedHtml)
  ) {
    return existingState;
  }

  try {
    await setTabState(tabId, {
      url: tabUrl,
      status: 'scanning',
      originalHtml: currentHtml,
      repairedHtml: null,
      issues_before: null,
      issues_fixed: 0,
      issues_after: null,
      issues: [],
      summary: 'No repair performed yet. Run a repair to see the summary.',
    });

    const { total_issues, issues } = await postJson(CONFIG.ENDPOINTS.SCAN, {
      html: currentHtml,
    });

    const scannedState = await setTabState(tabId, {
      url: tabUrl,
      status: 'scanned',
      originalHtml: currentHtml,
      repairedHtml: null,
      issues_before: total_issues,
      issues_fixed: 0,
      issues_after: total_issues,
      issues: issues || [],
      summary: 'No repair performed yet. Run a repair to see the summary.',
    });

    const { autoRepair } = await chrome.storage.local.get({ autoRepair: false });
    if (autoRepair && total_issues > 0) {
      return await executeRepairInternal(tabId, tabUrl, currentHtml, issues || []);
    }

    return scannedState;
  } catch (error) {
    console.error(`[BR1DG3 Background] Error on tab ${tabId}:`, error);
    return await setTabState(tabId, {
      url: tabUrl,
      status: 'error',
      originalHtml: null,
      repairedHtml: null,
      error: error.message || 'Scan/repair failed. Is the backend running?',
    });
  }
}

async function runRepairOnly(tabId, tabUrl) {
  const existingState = await getTabState(tabId);

  // 1. Track ongoing scan/repair: do not start another if one is already running
  if (
    existingState &&
    (existingState.status === 'scanning' || existingState.status === 'repairing')
  ) {
    return existingState;
  }

  try {
    const currentHtml = existingState?.originalHtml || (await getTabHtml(tabId));
    return await executeRepairInternal(
      tabId,
      tabUrl,
      currentHtml,
      existingState?.issues || []
    );
  } catch (error) {
    console.error(`[BR1DG3 Background] Repair error on tab ${tabId}:`, error);
    return await setTabState(tabId, {
      url: tabUrl,
      status: 'error',
      error: error.message || 'Repair failed. Is the backend running?',
    });
  }
}

chrome.runtime.onInstalled.addListener(async () => {
  const { autoRepair } = await chrome.storage.local.get({ autoRepair: false });
  await chrome.storage.local.set({ autoRepair: Boolean(autoRepair) });
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab && tab.url) {
    runScanAndMaybeRepair(tabId, tab.url, { forceScan: false });
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.local.remove(getTabStateKey(tabId));
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.type) return false;

  if (message.type === 'SCAN_TAB') {
    runScanAndMaybeRepair(message.tabId, message.url, {
      forceScan: Boolean(message.forceScan),
    })
      .then((state) => sendResponse({ ok: true, state }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  if (message.type === 'REPAIR_TAB') {
    runRepairOnly(message.tabId, message.url)
      .then((state) => sendResponse({ ok: true, state }))
      .catch((err) => sendResponse({ ok: false, error: err.message }));
    return true;
  }

  return false;
});
