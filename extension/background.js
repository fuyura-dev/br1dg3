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
  const key = getTabStateKey(tabId);
  try {
    await chrome.storage.local.set({
      [key]: nextState,
    });
  } catch (err) {
    if (String(err).includes('quota') || String(err).includes('kQuotaBytes') || String(err).includes('QuotaExceeded')) {
      console.warn(`[BR1DG3 Background] Storage quota exceeded. Pruning old tab states...`);
      try {
        const all = await chrome.storage.local.get(null);
        const otherKeys = Object.keys(all).filter((k) => k.startsWith('tabState_') && k !== key);
        if (otherKeys.length > 0) {
          await chrome.storage.local.remove(otherKeys);
        }
        await chrome.storage.local.set({ [key]: nextState });
      } catch (_) {
        // Fallback: trim oversized HTML if page is massive
        const compactState = {
          ...nextState,
          originalHtml: nextState.originalHtml ? nextState.originalHtml.slice(0, 500000) : null,
          repairedHtml: null,
        };
        await chrome.storage.local.set({ [key]: compactState }).catch(() => {});
      }
    } else {
      console.error(`[BR1DG3 Background] Error setting tab state:`, err);
    }
  }
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
        const bodyStyles = Array.from(document.body.querySelectorAll('style'));
        for (const attr of Array.from(newDoc.body.attributes)) {
          document.body.setAttribute(attr.name, attr.value);
        }
        document.body.innerHTML = newDoc.body.innerHTML;
        for (const styleEl of bodyStyles) {
          document.body.appendChild(styleEl);
        }
      }

      let soundPlayed = false;
      try {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
          const ctx = new AudioContextClass();
          const playChime = () => {
            const now = ctx.currentTime;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'sine';
            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.frequency.setValueAtTime(587.33, now);
            osc.frequency.setValueAtTime(880.0, now + 0.12);

            gain.gain.setValueAtTime(0, now);
            gain.gain.linearRampToValueAtTime(0.18, now + 0.02);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.38);

            osc.start(now);
            osc.stop(now + 0.38);
            soundPlayed = true;
          };

          if (ctx.state === 'suspended') {
            ctx.resume().then(playChime).catch(() => {});
          } else {
            playChime();
          }
        }
      } catch (_) {}

      return {
        html: document.documentElement ? document.documentElement.outerHTML : '',
        soundPlayed,
      };
    },
    args: [html],
  });
  return {
    html: result?.html || html,
    soundPlayed: Boolean(result?.soundPlayed),
  };
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
  const { html: liveRepairedHtml, soundPlayed } = await injectRepairedHtml(tabId, fixed_html);

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
    soundPlayed,
  });

  return repairedState;
}

async function runScanAndMaybeRepair(tabId, tabUrl, { forceScan = false } = {}) {
  if (!isScannableUrl(tabUrl)) return null;

  const existingState = await getTabState(tabId);

  // 1. Track ongoing scan/repair: only block if not forceScan and not stale (> 30s)
  if (
    existingState &&
    (existingState.status === 'scanning' || existingState.status === 'repairing')
  ) {
    const isStale = Date.now() - (existingState.updatedAt || 0) > 30000;
    if (!forceScan && !isStale) {
      return existingState;
    }
  }

  let currentHtml = '';
  try {
    currentHtml = await getTabHtml(tabId);
  } catch (err) {
    console.error(`[BR1DG3 Background] Failed to get HTML for tab ${tabId}:`, err);
    const isFileUrl = tabUrl && tabUrl.startsWith('file://');
    return await setTabState(tabId, {
      url: tabUrl,
      status: 'error',
      originalHtml: null,
      repairedHtml: null,
      error: isFileUrl
        ? 'Cannot access local file. Please enable "Allow access to file URLs" in chrome://extensions -> BR1DG3 Details.'
        : `Cannot access webpage DOM: ${err.message || err}`,
    });
  }
  if (!currentHtml) {
    return await setTabState(tabId, {
      url: tabUrl,
      status: 'error',
      originalHtml: null,
      repairedHtml: null,
      error: 'Page DOM is empty or not yet loaded. Please refresh the page and try again.',
    });
  }

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

  // 1. Track ongoing scan/repair: do not start another if one is already running and fresh (< 60s)
  if (
    existingState &&
    (existingState.status === 'scanning' || existingState.status === 'repairing')
  ) {
    const isStale = Date.now() - (existingState.updatedAt || 0) > 60000;
    if (!isStale) {
      return existingState;
    }
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

async function getTabOriginalHtml(tabId) {
  const tabState = await getTabState(tabId);
  if (tabState?.originalHtml) return tabState.originalHtml;
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => (document.documentElement ? document.documentElement.outerHTML : ''),
    });
    return result || '';
  } catch (_) {
    return '';
  }
}

async function openStudio(tabId) {
  const html = await getTabOriginalHtml(tabId);
  const tab = await chrome.tabs.create({
    url: "http://127.0.0.1:5173/studio?extension=1"
  });

  const listener = async (tabId, changeInfo) => {
    if (tabId !== tab.id || changeInfo.status !== "complete") {
      return;
    }

    chrome.tabs.onUpdated.removeListener(listener);

    await chrome.scripting.executeScript({
      target: { tabId },
      func: (html) => {
        window.postMessage(
          {
            source: "BR1DG3",
            html
          },
          "*"
        );
      },
      args: [html]
    });
  };

  chrome.tabs.onUpdated.addListener(listener);
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

  if (message.type === 'OPEN_STUDIO') {
    openStudio(message.tabId);
  }
  return false;
});
