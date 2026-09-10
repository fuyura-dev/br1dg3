document.addEventListener('DOMContentLoaded', () => {
  // Get the necessary elements from the DOM
  const autoRepairToggle = document.querySelector('.switch input');
  const statusBadge = document.querySelector('.status-badge');
  const rescanBtn = document.querySelectorAll('.btn-primary')[0];
  const viewSummaryBtn = document.querySelectorAll('.btn-primary')[1];
  const restoreBtn = document.querySelector('.btn-outline');

  // Handle the Auto-Repair ON/OFF toggle switch
  autoRepairToggle.addEventListener('change', (event) => {
    if (event.target.checked) {
      // Update UI when the switch is toggled ON
      statusBadge.textContent = 'ON';
      statusBadge.style.color = 'var(--success-text)';
      statusBadge.style.borderColor = 'var(--success-text)';
    } else {
      // Update UI when the switch is toggled OFF
      statusBadge.textContent = 'OFF';
      statusBadge.style.color = 'var(--text-muted)';
      statusBadge.style.borderColor = 'var(--text-muted)';
    }
  });

  // Button click event listeners (Placeholder logic for now)
  rescanBtn.addEventListener('click', () => {
    console.log('Re-scanning the current webpage...');
    rescanBtn.textContent = 'Scanning...';
    
    // Simulate a 1-second scanning delay
    setTimeout(() => {
      rescanBtn.textContent = 'Re-scan Page';
    }, 1000);
  });

  viewSummaryBtn.addEventListener('click', () => {
    console.log('Opening summary report...');
    // Add logic here to open a summary report in a new tab or modal
  });

  restoreBtn.addEventListener('click', () => {
    console.log('Restoring original webpage state...');
  });
});document.addEventListener('DOMContentLoaded', () => {
  // Get the necessary elements from the DOM
  const autoRepairToggle = document.querySelector('.switch input');
  const statusBadge = document.querySelector('.status-badge');
  const rescanBtn = document.querySelectorAll('.btn-primary')[0];
  const viewSummaryBtn = document.querySelectorAll('.btn-primary')[1];
  const restoreBtn = document.querySelector('.btn-outline');

  // Handle the Auto-Repair ON/OFF toggle switch
  autoRepairToggle.addEventListener('change', (event) => {
    if (event.target.checked) {
      // Update UI when the switch is toggled ON
      statusBadge.textContent = 'ON';
      statusBadge.style.color = 'var(--success-text)';
      statusBadge.style.borderColor = 'var(--success-text)';
    } else {
      // Update UI when the switch is toggled OFF
      statusBadge.textContent = 'OFF';
      statusBadge.style.color = 'var(--text-muted)';
      statusBadge.style.borderColor = 'var(--text-muted)';
    }
  });

  // Button click event listeners (Placeholder logic for now)
  rescanBtn.addEventListener('click', () => {
    console.log('Re-scanning the current webpage...');
    rescanBtn.textContent = 'Scanning...';
    
    // Simulate a 1-second scanning delay
    setTimeout(() => {
      rescanBtn.textContent = 'Re-scan Page';
    }, 1000);
  });

  viewSummaryBtn.addEventListener('click', () => {
    console.log('Opening summary report...');
    // Add logic here to open a summary report in a new tab or modal
  });

  restoreBtn.addEventListener('click', () => {
    console.log('Restoring original webpage state...');
  });
});