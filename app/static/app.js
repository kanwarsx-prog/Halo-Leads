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

    // Delete Organisation Handler
    const deleteOrgBtn = document.getElementById('delete-org-btn');
    if (deleteOrgBtn) {
        deleteOrgBtn.addEventListener('click', async () => {
            if (!confirm('Are you sure you want to delete this organisation? All research runs and assessments will be permanently lost.')) {
                return;
            }

            const orgId = deleteOrgBtn.dataset.orgId;
            const originalText = deleteOrgBtn.textContent;
            deleteOrgBtn.textContent = 'Deleting...';
            deleteOrgBtn.disabled = true;

            try {
                const response = await fetch(`/organisations/${orgId}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    showToast('Organisation deleted successfully!', 'success');
                    setTimeout(() => window.location.href = '/ui', 1000);
                } else {
                    const errData = await response.json();
                    showToast(errData.detail || 'Failed to delete organisation', 'error');
                }
            } catch (error) {
                console.error(error);
                showToast('A network error occurred.', 'error');
            } finally {
                deleteOrgBtn.textContent = originalText;
                deleteOrgBtn.disabled = false;
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
                    const data = await response.json();
                    const runId = data.run_id;
                    
                    const pollInterval = setInterval(async () => {
                        try {
                            const progressRes = await fetch(`/organisations/prospecting/runs/${runId}/progress`);
                            if (progressRes.ok) {
                                const progress = await progressRes.json();
                                
                                if (progress.status === 'completed') {
                                    clearInterval(pollInterval);
                                    spinner.innerText = 'Prospecting complete!';
                                    showToast('Prospecting run completed!', 'success');
                                    setTimeout(() => window.location.reload(), 1500);
                                } else if (progress.status === 'failed') {
                                    clearInterval(pollInterval);
                                    showToast(progress.message || 'Prospecting failed', 'error');
                                    btn.textContent = originalText;
                                    btn.disabled = false;
                                    spinner.style.display = 'none';
                                } else {
                                    spinner.innerText = progress.message;
                                }
                            }
                        } catch (e) {
                            console.error('Polling error:', e);
                        }
                    }, 1500);
                } else {
                    const errData = await response.json();
                    showToast(errData.detail || 'Failed to run prospecting', 'error');
                    btn.textContent = originalText;
                    btn.disabled = false;
                    spinner.style.display = 'none';
                }
            } catch (error) {
                console.error(error);
                showToast('A network error occurred.', 'error');
                btn.textContent = originalText;
                btn.disabled = false;
                spinner.style.display = 'none';
            }
        });
    }

    // Stage Select Dropdowns
    const stageSelects = document.querySelectorAll('.stage-select, #stage-select');
    stageSelects.forEach(select => {
        select.addEventListener('change', async (e) => {
            const orgId = e.target.dataset.orgId;
            const newStage = e.target.value;
            
            try {
                const response = await fetch(`/organisations/${orgId}/stage`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pipeline_stage: newStage })
                });
                
                if (!response.ok) throw new Error('Failed to update stage');
                
                showToast('Stage updated successfully', 'success');
                // Reload the page to update the dashboard metrics
                if (window.location.pathname === '/ui') {
                    setTimeout(() => window.location.reload(), 500);
                }
            } catch (error) {
                console.error(error);
                showToast('Error updating stage', 'error');
            }
        });
    });

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
    // Draft Email Buttons
    const draftEmailBtns = document.querySelectorAll('.draft-email-btn');
    draftEmailBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const orgId = e.target.dataset.orgId;
            const contactId = e.target.dataset.contactId;
            const row = document.getElementById(`email-draft-row-${contactId}`);
            const textarea = document.getElementById(`email-draft-${contactId}`);
            const spinner = row.querySelector('.draft-spinner');
            
            row.style.display = 'table-row';
            spinner.style.display = 'inline';
            btn.disabled = true;
            btn.innerText = 'Drafting...';
            
            try {
                const response = await fetch(`/ui/organisations/${orgId}/contacts/${contactId}/draft-email`, {
                    method: 'POST'
                });
                
                if (!response.ok) throw new Error('Failed to generate draft');
                
                const data = await response.json();
                textarea.value = data.draft;
                row.querySelector('.send-email-btn').style.display = 'inline-block';
                
                showToast('Email drafted successfully', 'success');
            } catch (error) {
                console.error(error);
                showToast('Error drafting email', 'error');
            } finally {
                spinner.style.display = 'none';
                btn.disabled = false;
                btn.innerText = 'Draft Email (AI)';
            }
        });
    });

    // Send Email Buttons
    const sendEmailBtns = document.querySelectorAll('.send-email-btn');
    sendEmailBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const orgId = btn.dataset.orgId;
            const contactId = btn.dataset.contactId;
            const textarea = document.getElementById(`email-draft-${contactId}`);
            const emailInput = document.getElementById(`email-to-${contactId}`);
            const attachCheckbox = document.getElementById(`email-attach-${contactId}`);
            
            btn.disabled = true;
            btn.innerText = 'Sending...';
            
            try {
                const response = await fetch(`/ui/organisations/${orgId}/contacts/${contactId}/send-email`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        draft_text: textarea.value,
                        recipient_email: emailInput.value,
                        include_attachment: attachCheckbox.checked
                    })
                });
                
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || 'Failed to send email');
                
                showToast('Email sent successfully!', 'success');
                btn.innerText = 'Sent ✓';
                btn.classList.remove('btn-primary');
                btn.classList.add('btn-secondary');
            } catch (error) {
                console.error(error);
                alert("Error sending email: " + (error.message || "Unknown error"));
                showToast(error.message || 'Error sending email', 'error');
                btn.disabled = false;
                btn.innerText = 'Send Email';
            }
        });
    });

    // Deep Dive Buttons
    const deepDiveBtns = document.querySelectorAll('.deep-dive-btn');
    deepDiveBtns.forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const orgId = e.target.dataset.orgId;
            const contactId = e.target.dataset.contactId;
            const notesCell = document.getElementById(`contact-notes-${contactId}`);
            
            btn.disabled = true;
            btn.innerText = 'Researching...';
            notesCell.innerHTML = '<span style="color: var(--warning);">Agent is hunting...</span>';
            
            try {
                const response = await fetch(`/ui/organisations/${orgId}/contacts/${contactId}/deep-research`, {
                    method: 'POST'
                });
                
                if (!response.ok) throw new Error('Failed to deep dive');
                
                const data = await response.json();
                notesCell.innerHTML = marked.parse(data.notes);
                
                showToast('Deep dive completed successfully', 'success');
                setTimeout(() => window.location.reload(), 1500);
            } catch (error) {
                console.error(error);
                showToast('Error researching contact', 'error');
                notesCell.textContent = 'Research failed.';
                btn.disabled = false;
                btn.innerText = 'Deep Dive (AI)';
            }
        });
    });

    // Manual Contact Form
    const addContactForm = document.getElementById('add-contact-form');
    if (addContactForm) {
        addContactForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const orgId = addContactForm.dataset.orgId;
            const btn = document.getElementById('manual-submit-btn');
            const name = document.getElementById('manual-name').value;
            const jobTitle = document.getElementById('manual-job-title').value;
            const email = document.getElementById('manual-email').value;
            const linkedin = document.getElementById('manual-linkedin').value;

            btn.disabled = true;
            btn.innerText = 'Saving...';

            try {
                const response = await fetch(`/ui/organisations/${orgId}/contacts/manual`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: name,
                        job_title: jobTitle,
                        email: email || null,
                        linkedin_url: linkedin || null
                    })
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Failed to add contact');
                }

                showToast('Contact added successfully', 'success');
                setTimeout(() => window.location.reload(), 1000);
            } catch (error) {
                console.error(error);
                alert("Error: " + (error.message || "Unknown error"));
                showToast(error.message || 'Error adding contact', 'error');
                btn.disabled = false;
                btn.innerText = 'Save Contact';
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

