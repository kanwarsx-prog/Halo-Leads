/**
 * SMM Agent
 * Clean, minimal slide-over assistant for checking school status,
 * drafting emails, taking notes, and logging meetings.
 */
(function () {
    const STORAGE_KEY = 'smm_agent_chat_history_v2';

    function getCurrentSchoolContext() {
        const match = window.location.pathname.match(/\/seemymind\/ui\/schools\/([a-zA-Z0-9\-]+)/);
        if (!match) return { id: null, name: null };
        const h1 = document.querySelector('h1');
        return {
            id: match[1],
            name: h1 ? h1.textContent.trim() : null
        };
    }

    function loadHistory() {
        try {
            return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]');
        } catch (e) {
            return [];
        }
    }

    function saveHistory(history) {
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(-20)));
        } catch (e) {}
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function formatAgentMarkdown(text) {
        let html = escapeHtml(text);
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color: var(--teal); font-weight: 600; text-decoration: underline;">$1</a>');
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    function initAgentUI() {
        if (document.getElementById('smmAgentDrawer')) return;

        // Floating bottom-right button
        const fab = document.createElement('button');
        fab.id = 'smmAgentFab';
        fab.type = 'button';
        fab.className = 'smm-agent-fab';
        fab.title = 'Open SMM Agent (Ctrl+K)';
        fab.innerHTML = '<span>✨</span> <span>SMM Agent</span>';
        fab.onclick = () => toggleAgentDrawer();
        document.body.appendChild(fab);

        // Clean Slide-over Drawer
        const ctx = getCurrentSchoolContext();
        const drawer = document.createElement('div');
        drawer.id = 'smmAgentDrawer';
        drawer.className = 'smm-agent-drawer';
        drawer.innerHTML = `
            <div class="smm-agent-header">
                <div style="display: flex; align-items: center; gap: 0.45rem;">
                    <span style="font-size: 1rem;">✨</span>
                    <strong style="font-size: 0.96rem; color: var(--ink);">SMM Agent</strong>
                    ${ctx.name ? `<span class="badge badge-gray" style="font-size: 0.68rem; font-weight: 500;">${escapeHtml(ctx.name)}</span>` : ''}
                </div>
                <div style="display: flex; align-items: center; gap: 0.35rem;">
                    <button type="button" onclick="window.smmClearAgentChat()" class="btn btn-secondary btn-sm" title="Clear chat" style="padding: 0.22rem 0.5rem; font-size: 0.72rem;">Clear</button>
                    <button type="button" onclick="window.toggleAgentDrawer(false)" class="btn btn-secondary btn-sm" title="Close" style="padding: 0.22rem 0.5rem; font-size: 0.82rem;">✕</button>
                </div>
            </div>

            <div class="smm-agent-chips">
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('Status of ')">School Status</button>
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('Draft an email to ')">Draft Email</button>
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('Add a note for ')">Take Note</button>
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('Schedule a meeting with ')">Log Meeting</button>
                <button type="button" class="smm-chip" onclick="window.smmSendQuickPrompt('What meetings and follow-ups do I have coming up?')">Schedule</button>
            </div>

            <div id="smmAgentRefreshBanner" class="smm-agent-refresh-banner" style="display: none;">
                <span>✓ Saved changes</span>
                <button type="button" onclick="window.location.reload()" class="btn btn-primary btn-sm" style="padding: 0.18rem 0.5rem; font-size: 0.72rem;">↻ Refresh</button>
            </div>

            <div id="smmAgentMessages" class="smm-agent-messages"></div>

            <form id="smmAgentForm" class="smm-agent-input-bar" onsubmit="window.smmSubmitAgentMessage(event)">
                <input type="text" id="smmAgentInput" autocomplete="off" placeholder="Ask SMM Agent..." />
                <button type="submit" id="smmAgentSendBtn" class="btn btn-primary" style="height: 36px; padding: 0 0.85rem;">Send</button>
            </form>
        `;
        document.body.appendChild(drawer);

        renderStoredMessages();

        document.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                toggleAgentDrawer();
            } else if (e.key === 'Escape' && drawer.classList.contains('open')) {
                toggleAgentDrawer(false);
            }
        });
    }

    function renderStoredMessages() {
        const container = document.getElementById('smmAgentMessages');
        if (!container) return;
        const history = loadHistory();
        container.innerHTML = '';

        if (history.length === 0) {
            const ctx = getCurrentSchoolContext();
            const greeting = ctx.name
                ? `How can I help with <strong>${escapeHtml(ctx.name)}</strong>? Ask me for their status, draft an email, add a note, or schedule a meeting.`
                : `How can I help? Ask me to check a school's status, draft an email, add a note, or schedule a meeting.`;
            container.innerHTML = `
                <div class="smm-msg smm-msg-assistant">
                    <div class="smm-msg-bubble">${greeting}</div>
                </div>
            `;
            return;
        }

        history.forEach(item => {
            appendMessageDOM(item.role, item.content, item.actions || []);
        });
        container.scrollTop = container.scrollHeight;
    }

    function appendMessageDOM(role, content, actions = []) {
        const container = document.getElementById('smmAgentMessages');
        if (!container) return;

        const wrap = document.createElement('div');
        wrap.className = `smm-msg smm-msg-${role}`;

        let actionsHtml = '';
        if (actions && actions.length > 0) {
            const badges = actions.map(a => {
                const link = a.school_id
                    ? `<a href="/seemymind/ui/schools/${escapeHtml(a.school_id)}" style="color: inherit; text-decoration: underline; margin-left: 0.25rem;">Open &rarr;</a>`
                    : '';
                return `<div class="smm-action-pill">✓ ${escapeHtml(a.label)} ${link}</div>`;
            }).join('');

            const emailAction = actions.find(a => a.email_draft && a.email_draft.body);
            let copyBtn = '';
            if (emailAction) {
                const encoded = encodeURIComponent(`Subject: ${emailAction.email_draft.subject}\n\n${emailAction.email_draft.body}`);
                copyBtn = `<button type="button" class="btn btn-secondary btn-sm" style="margin-top: 0.3rem; font-size: 0.72rem;" onclick="navigator.clipboard.writeText(decodeURIComponent('${encoded}')); this.textContent='✓ Copied'; setTimeout(()=>this.textContent='Copy Email', 2000);">Copy Email</button>`;
            }
            actionsHtml = `<div class="smm-actions-list">${badges}${copyBtn}</div>`;
        }

        wrap.innerHTML = `
            ${actionsHtml}
            <div class="smm-msg-bubble">${role === 'user' ? escapeHtml(content) : formatAgentMarkdown(content)}</div>
        `;
        container.appendChild(wrap);
        container.scrollTop = container.scrollHeight;
    }

    window.toggleAgentDrawer = function (forceState) {
        const drawer = document.getElementById('smmAgentDrawer');
        if (!drawer) return;
        const isOpen = typeof forceState === 'boolean' ? forceState : !drawer.classList.contains('open');
        drawer.classList.toggle('open', isOpen);
        if (isOpen) {
            setTimeout(() => {
                const inp = document.getElementById('smmAgentInput');
                if (inp) inp.focus();
            }, 120);
        }
    };

    window.smmFillPrompt = function (prefix) {
        const ctx = getCurrentSchoolContext();
        const inp = document.getElementById('smmAgentInput');
        if (!inp) return;
        if (ctx.name && prefix.endsWith(' ')) {
            inp.value = `${prefix}${ctx.name}: `;
        } else {
            inp.value = prefix;
        }
        inp.focus();
    };

    window.smmSendQuickPrompt = function (text) {
        const inp = document.getElementById('smmAgentInput');
        if (!inp) return;
        inp.value = text;
        window.smmSubmitAgentMessage(new Event('submit'));
    };

    window.smmClearAgentChat = function () {
        sessionStorage.removeItem(STORAGE_KEY);
        const banner = document.getElementById('smmAgentRefreshBanner');
        if (banner) banner.style.display = 'none';
        renderStoredMessages();
    };

    window.smmSubmitAgentMessage = async function (e) {
        if (e && e.preventDefault) e.preventDefault();
        const inp = document.getElementById('smmAgentInput');
        const sendBtn = document.getElementById('smmAgentSendBtn');
        const container = document.getElementById('smmAgentMessages');
        if (!inp || !container) return;

        const message = inp.value.trim();
        if (!message) return;

        inp.value = '';
        const history = loadHistory();
        appendMessageDOM('user', message);

        const thinkingEl = document.createElement('div');
        thinkingEl.className = 'smm-msg smm-msg-assistant';
        thinkingEl.innerHTML = `<div class="smm-msg-bubble" style="color: var(--soft);">Working...</div>`;
        container.appendChild(thinkingEl);
        container.scrollTop = container.scrollHeight;

        sendBtn.disabled = true;
        const ctx = getCurrentSchoolContext();

        try {
            const res = await fetch('/seemymind/agent/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    history: history.map(h => ({ role: h.role, content: h.content })),
                    current_school_id: ctx.id
                })
            });
            const data = await res.json();
            thinkingEl.remove();

            const reply = data.reply || 'Done.';
            const actions = data.actions_taken || [];
            appendMessageDOM('assistant', reply, actions);

            history.push({ role: 'user', content: message });
            history.push({ role: 'assistant', content: reply, actions: actions });
            saveHistory(history);

            if (data.mutated) {
                const banner = document.getElementById('smmAgentRefreshBanner');
                if (banner) banner.style.display = 'flex';
            }
        } catch (err) {
            thinkingEl.remove();
            appendMessageDOM('assistant', 'Could not reach SMM Agent. Please try again.');
        } finally {
            sendBtn.disabled = false;
            inp.focus();
        }
    };

    document.addEventListener('DOMContentLoaded', initAgentUI);
})();
