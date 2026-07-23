document.addEventListener('DOMContentLoaded', () => {
    // Add Organisation Form Handler
    const addOrgForm = document.getElementById('add-org-form');
    if (addOrgForm) {
        addOrgForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const btn = addOrgForm.querySelector('button');
            const originalText = btn.textContent;
            btn.textContent = 'Adding...';
            btn.disabled = true;

            const formData = new FormData(addOrgForm);
            const data = Object.fromEntries(formData.entries());

            try {
                const response = await fetch('/organisations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    showToast('Organisation added successfully!', 'success');
                    addOrgForm.reset();
                    // Reload to show the new org in the list
                    setTimeout(() => window.location.reload(), 1000);
                } else {
                    const errData = await response.json();
                    showToast(errData.detail || 'Failed to add organisation', 'error');
                }
            } catch (error) {
                console.error(error);
                showToast('A network error occurred.', 'error');
            } finally {
                btn.textContent = originalText;
                btn.disabled = false;
            }
        });
    }

    // Add Prospecting Form Handler
    const prospectingForm = document.getElementById('prospecting-form');
    if (prospectingForm) {
        prospectingForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const btn = prospectingForm.querySelector('button');
            const spinner = document.getElementById('prospecting-spinner');
            const originalText = btn.textContent;
            btn.textContent = 'Hunting...';
            btn.disabled = true;
            spinner.style.display = 'block';

            const formData = new FormData(prospectingForm);
            const data = Object.fromEntries(formData.entries());

            try {
                const response = await fetch('/organisations/prospecting/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    const result = await response.json();
                    showToast(result.message || 'Prospecting complete!', 'success');
                    prospectingForm.reset();
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    const errData = await response.json();
                    showToast(errData.detail || 'Failed to run prospecting', 'error');
                }
            } catch (error) {
                console.error(error);
                showToast('A network error occurred.', 'error');
            } finally {
                btn.textContent = originalText;
                btn.disabled = false;
                spinner.style.display = 'none';
            }
        });
    }

    // Trigger Research Run Handler
    const triggerBtn = document.getElementById('trigger-research-btn');
    if (triggerBtn) {
        triggerBtn.addEventListener('click', async () => {
            const orgId = triggerBtn.dataset.orgId;
            const originalText = triggerBtn.textContent;
            triggerBtn.textContent = 'Initializing...';
            triggerBtn.disabled = true;
            triggerBtn.classList.add('loading');

            try {
                const response = await fetch(`/research/organisations/${orgId}/research_again`, {
                    method: 'POST'
                });

                if (!response.ok) {
                    const errData = await response.json();
                    showToast(errData.detail || 'Failed to start research', 'error');
                    throw new Error('Failed to start');
                }

                const data = await response.json();
                const runId = data.run_id;

                const pollInterval = setInterval(async () => {
                    try {
                        const progressRes = await fetch(`/research/organisations/${orgId}/runs/${runId}/progress`);
                        if (progressRes.ok) {
                            const progress = await progressRes.json();
                            
                            if (progress.status === 'completed') {
                                clearInterval(pollInterval);
                                triggerBtn.textContent = 'Complete!';
                                showToast('Research run completed!', 'success');
                                setTimeout(() => window.location.reload(), 1500);
                            } else if (progress.status === 'failed') {
                                clearInterval(pollInterval);
                                showToast(progress.message || 'Research failed', 'error');
                                triggerBtn.textContent = originalText;
                                triggerBtn.disabled = false;
                                triggerBtn.classList.remove('loading');
                            } else {
                                triggerBtn.textContent = progress.message;
                            }
                        }
                    } catch (e) {
                        console.error('Polling error:', e);
                    }
                }, 1500);
            } catch (error) {
                console.error(error);
                showToast('A network error occurred.', 'error');
                triggerBtn.textContent = originalText;
                triggerBtn.disabled = false;
                triggerBtn.classList.remove('loading');
            }
        });

        // Check if there is an active run on page load
        const activeRunId = triggerBtn.dataset.activeRunId;
        if (activeRunId) {
            triggerBtn.disabled = true;
            triggerBtn.classList.add('loading');
            const orgId = triggerBtn.dataset.orgId;
            const originalText = 'Run New Discovery';

            const pollInterval = setInterval(async () => {
                try {
                    const progressRes = await fetch(`/research/organisations/${orgId}/runs/${activeRunId}/progress`);
                    if (progressRes.ok) {
                        const progress = await progressRes.json();
                        
                        if (progress.status === 'completed') {
                            clearInterval(pollInterval);
                            triggerBtn.textContent = 'Complete!';
                            showToast('Research run completed!', 'success');
                            setTimeout(() => window.location.reload(), 1500);
                        } else if (progress.status === 'failed') {
                            clearInterval(pollInterval);
                            showToast(progress.message || 'Research failed', 'error');
                            triggerBtn.textContent = originalText;
                            triggerBtn.disabled = false;
                            triggerBtn.classList.remove('loading');
                        } else {
                            triggerBtn.textContent = progress.message;
                        }
                    }
                } catch (e) {
                    console.error('Polling error:', e);
                }
            }, 1500);
        }
    }
});

function showToast(message, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    if (type === 'error') {
        toast.style.borderLeftColor = 'var(--danger)';
    }
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
