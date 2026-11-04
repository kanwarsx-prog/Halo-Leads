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

// State for Filtering, Sorting, and Pagination
let currentPage = 1;
let pageSize = 25;
let currentSortColumn = -1;
let currentSortAsc = true;
let filteredRows = [];

function getFilterValues() {
  return {
    school: (document.getElementById('colSearchSchool')?.value || '').toLowerCase().trim(),
    phase: document.getElementById('colFilterPhase')?.value || '',
    trust: (document.getElementById('colSearchTrust')?.value || '').toLowerCase().trim(),
    sen: document.getElementById('colFilterSen')?.value || '',
    ofsted: document.getElementById('colFilterOfsted')?.value || '',
    priority: document.getElementById('colFilterPriority')?.value || '',
    stage: document.getElementById('colFilterStage')?.value || ''
  };
}

function filterSchools() {
  const filters = getFilterValues();
  const allRows = Array.from(document.querySelectorAll('#schoolsTable tbody tr.school-row'));
  
  filteredRows = allRows.filter(row => {
    const name = row.dataset.name || '';
    const postcode = row.dataset.postcode || '';
    const phase = row.dataset.phase || '';
    const mat = row.dataset.mat || '';
    const la = row.dataset.la || '';
    const sen = parseFloat(row.dataset.sen) || 0;
    const ofsted = row.dataset.ofsted || '';
    const priority = row.dataset.priority || '';
    const stage = row.dataset.stage || '';

    // 1. School name or postcode filter
    if (filters.school && !name.includes(filters.school) && !postcode.includes(filters.school)) {
      return false;
    }

    // 2. Phase filter
    if (filters.phase && !phase.toLowerCase().includes(filters.phase.toLowerCase())) {
      return false;
    }

    // 3. Trust or LA filter
    if (filters.trust && !mat.includes(filters.trust) && !la.includes(filters.trust)) {
      return false;
    }

    // 4. SEN % filter
    if (filters.sen === '16' && sen < 16.0) return false;
    if (filters.sen === 'recorded' && sen <= 0) return false;

    // 5. Ofsted filter
    if (filters.ofsted) {
      if (filters.ofsted === 'Pending' && !ofsted.toLowerCase().includes('pending')) return false;
      if (filters.ofsted !== 'Pending' && !ofsted.toLowerCase().includes(filters.ofsted.toLowerCase())) return false;
    }

    // 6. Priority filter
    if (filters.priority && priority !== filters.priority) return false;

    // 7. Stage filter
    if (filters.stage && stage !== filters.stage) return false;

    return true;
  });

  currentPage = 1;
  renderPaginatedTable();
}

function renderPaginatedTable() {
  const allRows = Array.from(document.querySelectorAll('#schoolsTable tbody tr.school-row'));
  allRows.forEach(r => r.style.display = 'none');

  const total = filteredRows.length;
  const countLabel = document.getElementById('schoolsCountLabel');
  if (countLabel) {
    countLabel.innerText = `Showing ${total} of ${allRows.length} schools`;
  }

  const effectiveSize = pageSize === 'all' ? total : parseInt(pageSize, 10);
  const totalPages = Math.max(1, Math.ceil(total / effectiveSize));
  if (currentPage > totalPages) currentPage = totalPages;

  const startIndex = (currentPage - 1) * effectiveSize;
  const endIndex = Math.min(startIndex + effectiveSize, total);

  for (let i = startIndex; i < endIndex; i++) {
    if (filteredRows[i]) {
      filteredRows[i].style.display = '';
    }
  }

  // Update pagination bar
  const pageInfo = document.getElementById('pageInfoLabel');
  if (pageInfo) {
    if (total === 0) {
      pageInfo.innerText = 'No matching schools found';
    } else {
      pageInfo.innerText = `Showing ${startIndex + 1}–${endIndex} of ${total} schools`;
    }
  }

  const pageNumDisplay = document.getElementById('pageNumDisplay');
  if (pageNumDisplay) {
    pageNumDisplay.innerText = `Page ${currentPage} of ${totalPages}`;
  }

  const prevBtn = document.getElementById('prevPageBtn');
  const firstBtn = document.getElementById('firstPageBtn');
  const nextBtn = document.getElementById('nextPageBtn');
  const lastBtn = document.getElementById('lastPageBtn');

  if (prevBtn) prevBtn.disabled = (currentPage <= 1);
  if (firstBtn) firstBtn.disabled = (currentPage <= 1);
  if (nextBtn) nextBtn.disabled = (currentPage >= totalPages);
  if (lastBtn) lastBtn.disabled = (currentPage >= totalPages);
}

function goToPage(page) {
  const effectiveSize = pageSize === 'all' ? filteredRows.length : parseInt(pageSize, 10);
  const totalPages = Math.max(1, Math.ceil(filteredRows.length / effectiveSize));
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  renderPaginatedTable();
}

function changePageSize(val) {
  pageSize = val;
  currentPage = 1;
  renderPaginatedTable();
}

function resetAllFilters() {
  const elIds = ['colSearchSchool', 'colFilterPhase', 'colSearchTrust', 'colFilterSen', 'colFilterOfsted', 'colFilterPriority', 'colFilterStage'];
  elIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  filterSchools();
}

function sortTable(columnIndex, type) {
  const tbody = document.querySelector('#schoolsTable tbody');
  if (!tbody) return;

  if (currentSortColumn === columnIndex) {
    currentSortAsc = !currentSortAsc;
  } else {
    currentSortColumn = columnIndex;
    currentSortAsc = true;
  }

  // Update sort icons
  for (let i = 0; i <= 6; i++) {
    const icon = document.getElementById(`sortIcon${i}`);
    if (icon) {
      if (i === columnIndex) {
        icon.innerText = currentSortAsc ? '▲' : '▼';
        icon.style.opacity = '1';
        icon.style.color = 'var(--teal)';
      } else {
        icon.innerText = '↕';
        icon.style.opacity = '0.5';
        icon.style.color = '';
      }
    }
  }

  const rows = Array.from(document.querySelectorAll('#schoolsTable tbody tr.school-row'));

  rows.sort((a, b) => {
    let valA, valB;

    switch (columnIndex) {
      case 0: // School name
        valA = a.dataset.name || '';
        valB = b.dataset.name || '';
        break;
      case 1: // Phase
        valA = a.dataset.phase || '';
        valB = b.dataset.phase || '';
        break;
      case 2: // Trust / LA
        valA = (a.dataset.mat || a.dataset.la || '');
        valB = (b.dataset.mat || b.dataset.la || '');
        break;
      case 3: // SEN %
        valA = parseFloat(a.dataset.sen) || 0;
        valB = parseFloat(b.dataset.sen) || 0;
        break;
      case 4: // Ofsted
        valA = a.dataset.ofsted || '';
        valB = b.dataset.ofsted || '';
        break;
      case 5: // Priority score
        valA = parseInt(a.dataset.score, 10) || 0;
        valB = parseInt(b.dataset.score, 10) || 0;
        break;
      case 6: // Stage
        valA = a.dataset.stage || '';
        valB = b.dataset.stage || '';
        break;
      default:
        return 0;
    }

    if (type === 'number') {
      return currentSortAsc ? (valA - valB) : (valB - valA);
    } else {
      return currentSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
  });

  // Re-append sorted rows to tbody
  rows.forEach(r => tbody.appendChild(r));

  // Re-filter and re-paginate
  filterSchools();
}

// Initialise pagination on page load
document.addEventListener('DOMContentLoaded', () => {
  const allRows = Array.from(document.querySelectorAll('#schoolsTable tbody tr.school-row'));
  filteredRows = allRows;
  renderPaginatedTable();
});

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
