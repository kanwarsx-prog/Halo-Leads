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

                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let buffer = "";

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\\n');
                    
                    // Keep the last incomplete line in the buffer
                    buffer = lines.pop();

                    for (const line of lines) {
                        if (!line.trim()) continue;
                        
                        try {
                            const data = JSON.parse(line);
                            
                            if (data.status === 'info') {
                                triggerBtn.textContent = data.message;
                            } else if (data.status === 'success') {
                                triggerBtn.textContent = 'Complete!';
                                showToast('Research run completed!', 'success');
                                setTimeout(() => window.location.reload(), 1500);
                            } else if (data.status === 'error') {
                                showToast(data.message || 'An error occurred', 'error');
                                triggerBtn.textContent = originalText;
                                triggerBtn.disabled = false;
                                triggerBtn.classList.remove('loading');
                            }
                        } catch (e) {
                            console.error("Failed to parse stream line:", line, e);
                        }
                    }
                }
            } catch (error) {
                console.error(error);
                showToast('A network error occurred.', 'error');
                triggerBtn.textContent = originalText;
                triggerBtn.disabled = false;
                triggerBtn.classList.remove('loading');
            }
        });
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
