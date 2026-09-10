document.addEventListener('DOMContentLoaded', () => {
  // Retrieve essential UI elements from the DOM
  const autoRepairToggle = document.querySelector('.switch input');
  const statusBadge = document.querySelector('.status-badge');
  const rescanBtn = document.querySelectorAll('.btn-primary')[0];
  const viewSummaryBtn = document.querySelectorAll('.btn-primary')[1];
  const restoreBtn = document.querySelector('.btn-outline');

  // Retrieve the stat elements we just added IDs to
  const statIssues = document.getElementById('stat-issues');
  const statImprovements = document.getElementById('stat-improvements');
  const statStructure = document.getElementById('stat-structure');
  const statResult = document.getElementById('stat-result');

  // Base URL for the local FastAPI backend
  const API_BASE_URL = 'http://127.0.0.1:8000/api';

  /**
   * Utility function to handle POST requests to the backend.
   * @param {string} endpoint - The API endpoint to call (e.g., '/scan').
   * @param {object} payload - The JSON data to send in the request body.
   * @returns {Promise<object>} - The JSON response from the server.
   */
  async function sendToBackend(endpoint, payload) {
    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });
      return await response.json();
    } catch (error) {
      console.error(`Error calling ${endpoint}:`, error);
      throw error;
    }
  }

  /**
   * Core function to scan the current webpage and send its HTML to the backend.
   * This can be triggered automatically on load or manually via the Re-scan button.
   */
  async function performScan() {
    // Update button state to indicate scanning is in progress
    rescanBtn.textContent = 'Scanning...';
    rescanBtn.disabled = true; 
    
    // Set stats to loading state
    statIssues.textContent = '...';
    statImprovements.textContent = '...';
    statStructure.textContent = '...';
    statResult.textContent = '...';
    
    try {
      // 1. Get the current active tab in Chrome
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      
      // 2. Inject a small script into the page to extract its HTML
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => document.documentElement.outerHTML,
      });
      
      // Extract the string result returned by the injected function
      const pageHTML = injectionResults[0].result;

      // 3. Send the HTML to the backend, matching the FastAPI ScanRequest model
      const result = await sendToBackend('/scan', { html: pageHTML });
      
      // 4. Update the UI dynamically with the results
      statIssues.textContent = result.total_issues;
      
      // Temporary placeholder logic for metrics not fully implemented in the backend yet
      statImprovements.textContent = '0'; // 0 because we only scanned, we haven't repaired yet
      statStructure.textContent = '1';    // 1 because we scanned 1 HTML document structure
      statResult.textContent = result.total_issues > 0 ? 'Needs Repair' : 'Clean';
      
    } catch (error) {
      console.error(error);
      alert('Error scanning page. Is the backend running, and does the extension have permissions?');
      
      // Reset stats on error
      statIssues.textContent = 'Error';
      statImprovements.textContent = '--';
      statStructure.textContent = '--';
      statResult.textContent = 'Failed';
    } finally {
      // Restore the original button state regardless of success or failure
      rescanBtn.textContent = 'Re-scan Page';
      rescanBtn.disabled = false;
    }
  }

  // ==========================================
  // AUTOMATIC TRIGGER: Run scan immediately when popup opens
  // ==========================================
  performScan();

  // Allow manual re-scanning if the user clicks the button
  rescanBtn.addEventListener('click', performScan);

  // Handle the Auto-Repair ON/OFF toggle switch
  autoRepairToggle.addEventListener('change', async (event) => {
    const isEnabled = event.target.checked;
    
    try {
      if (isEnabled) {
        statusBadge.textContent = 'Enabling...';
        await sendToBackend('/repair', { action: 'enable_auto_repair' });
        
        statusBadge.textContent = 'ON';
        statusBadge.style.color = 'var(--success-text)';
        statusBadge.style.borderColor = 'var(--success-text)';
      } else {
        statusBadge.textContent = 'Disabling...';
        await sendToBackend('/repair', { action: 'disable_auto_repair' });
        
        statusBadge.textContent = 'OFF';
        statusBadge.style.color = 'var(--text-muted)';
        statusBadge.style.borderColor = 'var(--text-muted)';
      }
    } catch (error) {
      alert('Failed to update Auto-Repair. Check if the backend is running.');
      event.target.checked = !isEnabled;
      statusBadge.textContent = !isEnabled ? 'ON' : 'OFF';
    }
  });

  // Handle the View Summary button click
  viewSummaryBtn.addEventListener('click', async () => {
    const originalText = viewSummaryBtn.textContent;
    viewSummaryBtn.textContent = 'Loading...';
    viewSummaryBtn.disabled = true;

    try {
      const result = await sendToBackend('/graph', { request: 'summary_data' });
      console.log('Graph/Summary data:', result);
    } catch (error) {
      alert('Error loading summary report.');
    } finally {
      viewSummaryBtn.textContent = originalText;
      viewSummaryBtn.disabled = false;
    }
  });

  // Handle the Restore button click
  restoreBtn.addEventListener('click', async () => {
    const originalText = restoreBtn.textContent;
    restoreBtn.textContent = 'Restoring...';
    restoreBtn.disabled = true;

    try {
      const result = await sendToBackend('/repair', { action: 'restore_original' });
      console.log('Restore result:', result);
      alert('Webpage restore command sent successfully!');
    } catch (error) {
      alert('Error restoring webpage.');
    } finally {
      restoreBtn.textContent = originalText;
      restoreBtn.disabled = false;
    }
  });
});