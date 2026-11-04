// See My Mind Education Lead Agent Frontend JS
const SMM_BASE = window.SMM_BASE || '/seemymind';

function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'flex';
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

// Stage change
async function updateStage(schoolId, stage) {
  try {
    const res = await fetch(`${SMM_BASE}/schools/${schoolId}/stage`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipeline_stage: stage })
    });
    if (res.ok) {
      window.location.reload();
    } else {
      alert('Failed to update stage');
    }
  } catch (err) {
    console.error(err);
    alert('Error connecting to server');
  }
}

// Trigger School Audit
async function triggerAudit(schoolId, btnElement) {
  const originalText = btnElement ? btnElement.innerHTML : '';
  if (btnElement) {
    btnElement.innerHTML = 'Starting discovery...';
    btnElement.disabled = true;
  }

  try {
    const res = await fetch(`${SMM_BASE}/research/schools/${schoolId}`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) {
      pollAudit(data.run_id, btnElement, originalText);
    } else {
      alert(data.detail || 'Failed to start discovery');
      if (btnElement) {
        btnElement.innerHTML = originalText;
        btnElement.disabled = false;
      }
    }
  } catch (err) {
    console.error(err);
    alert('Error connecting to server');
    if (btnElement) {
      btnElement.innerHTML = originalText;
      btnElement.disabled = false;
    }
  }
}

function pollAudit(runId, btnElement, originalText) {
  const interval = setInterval(async () => {
    try {
      const res = await fetch(`${SMM_BASE}/research/runs/${runId}`);
      const data = await res.json();
      if (btnElement && data.current_message) {
        btnElement.innerHTML = `<span style="animation: pulse 1.5s infinite;">⏳ ${data.current_message}</span>`;
      }

      if (data.status === 'completed') {
        clearInterval(interval);
        if (btnElement) btnElement.innerHTML = 'Discovery Complete! Reloading...';
        setTimeout(() => window.location.reload(), 1200);
      } else if (data.status === 'failed') {
        clearInterval(interval);
        alert('Discovery failed: ' + (data.error_message || 'Unknown error'));
        if (btnElement) {
          btnElement.innerHTML = originalText;
          btnElement.disabled = false;
        }
      }
    } catch (err) {
      console.error(err);
    }
  }, 3000);
}

// Tab Switching
function switchTab(evt, tabId) {
  const tabGroup = evt.target.closest('.card') || document;
  tabGroup.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  tabGroup.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

  evt.target.classList.add('active');
  const target = document.getElementById(tabId);
  if (target) target.classList.add('active');
}

// Copy to Clipboard
function copyText(elementId, btn) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const text = el.innerText || el.value;
  navigator.clipboard.writeText(text).then(() => {
    const oldText = btn.innerText;
    btn.innerText = 'Copied!';
    btn.style.backgroundColor = 'var(--success)';
    btn.style.color = '#fff';
    setTimeout(() => {
      btn.innerText = oldText;
      btn.style.backgroundColor = '';
      btn.style.color = '';
    }, 2000);
  });
}

// Print Letter
function printLetter() {
  window.print();
}

// Enhanced Multi-Attribute Table Filter
function filterSchools() {
  const queryInput = document.getElementById('schoolFilter');
  const stageSelect = document.getElementById('stageFilter');
  const prioritySelect = document.getElementById('priorityFilter');
  
  const query = queryInput ? queryInput.value.toLowerCase().trim() : '';
  const stage = stageSelect ? stageSelect.value : '';
  const priority = prioritySelect ? prioritySelect.value : '';
  
  const rows = document.querySelectorAll('#schoolsTable tbody tr');
  let visibleCount = 0;

  rows.forEach(row => {
    const text = row.innerText.toLowerCase();
    const rowStage = row.dataset.stage || '';
    const rowPriority = row.dataset.priority || '';

    const matchesQuery = !query || text.includes(query);
    const matchesStage = !stage || rowStage === stage;
    const matchesPriority = !priority || rowPriority === priority;

    if (matchesQuery && matchesStage && matchesPriority) {
      row.style.display = '';
      visibleCount++;
    } else {
      row.style.display = 'none';
    }
  });

  const countLabel = document.getElementById('schoolsCountLabel');
  if (countLabel) {
    countLabel.innerText = `Showing ${visibleCount} of ${rows.length} schools`;
  }
}

async function markTaskDone(taskId, btn) {
  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Updating...';
  }
  try {
    const res = await fetch(`${SMM_BASE}/schools/activities/${taskId}/complete`, {
      method: 'POST'
    });
    if (res.ok) {
      window.location.reload();
    } else {
      alert('Failed to update task');
      if (btn) {
        btn.disabled = false;
        btn.innerText = '✓ Complete';
      }
    }
  } catch (err) {
    console.error(err);
    if (btn) {
      btn.disabled = false;
      btn.innerText = '✓ Complete';
    }
  }
}
