/**
 * See My Mind In-App AI Agent Copilot
 * Self-contained slide-over assistant for checking school status, drafting emails,
 * taking CRM notes, logging meeting schedules, and updating pipeline stages.
 */
(function () {
    const STORAGE_KEY = 'smm_agent_chat_history_v1';

    function getCurrentSchoolContext() {
        const match = window.location.pathname.match(/\/seemymind\/ui\/schools\/([a-zA-Z0-9\-]+)/);
        if (!match) return { id: null, name: null };
        const h1 = document.querySelector('h1');
        return {
            id: match[1],
            name: h1 ? h1.textContent.trim() : 'Current School'
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
        // Bold **text**
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // Links [label](url)
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color: var(--teal); font-weight: 600; text-decoration: underline;">$1</a>');
        // Inline code `code`
        html = html.replace(/`([^`]+)`/g, '<code style="background: var(--gray-100); padding: 0.1rem 0.3rem; border-radius: 4px; font-size: 0.78rem;">$1</code>');
        // Line breaks
        html = html.replace(/\n/g, '<br>');
        return html;
    }

    function initAgentUI() {
        if (document.getElementById('smmAgentDrawer')) return;

        // 1. Add compact Agent button to <nav> if present
        const nav = document.querySelector('header nav');
        if (nav && !document.getElementById('navAgentBtn')) {
            const btn = document.createElement('button');
            btn.id = 'navAgentBtn';
            btn.type = 'button';
            btn.className = 'btn btn-primary';
            btn.style.cssText = 'background: linear-gradient(135deg, #1d625d 0%, #123b38 100%); gap: 0.3rem;';
            btn.title = 'Open AI Agent Assistant (Ctrl+K)';
            btn.innerHTML = '<span>✨</span> <span>Agent</span>';
            btn.onclick = () => toggleAgentDrawer(true);
            nav.insertBefore(btn, nav.firstChild);
        }

        // 2. Floating Bottom-Right FAB
        const fab = document.createElement('button');
        fab.id = 'smmAgentFab';
        fab.type = 'button';
        fab.className = 'smm-agent-fab';
        fab.title = 'Ask See My Mind Agent (Ctrl+K)';
        fab.innerHTML = '<span>✨</span> <span>Ask Agent</span>';
        fab.onclick = () => toggleAgentDrawer();
        document.body.appendChild(fab);

        // 3. Slide-over Drawer HTML
        const ctx = getCurrentSchoolContext();
        const drawer = document.createElement('div');
        drawer.id = 'smmAgentDrawer';
        drawer.className = 'smm-agent-drawer';
        drawer.innerHTML = `
            <div class="smm-agent-header">
                <div>
                    <div style="display: flex; align-items: center; gap: 0.45rem;">
                        <span style="font-size: 1.1rem;">✨</span>
                        <strong style="font-size: 0.98rem; color: var(--ink);">See My Mind Agent</strong>
                        <span class="badge badge-mint" style="font-size: 0.65rem;">Live CRM Tools</span>
                    </div>
                    <div id="smmAgentContextBadge" style="font-size: 0.73rem; color: var(--soft); margin-top: 0.2rem;">
                        ${ctx.id ? `📍 Context: <strong>${escapeHtml(ctx.name)}</strong>` : '🌐 Connected across all schools, contacts & schedules'}
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 0.35rem;">
                    <button type="button" onclick="window.smmClearAgentChat()" class="btn btn-secondary btn-sm" title="Clear conversation" style="padding: 0.25rem 0.5rem; font-size: 0.72rem;">Clear</button>
                    <button type="button" onclick="window.toggleAgentDrawer(false)" class="btn btn-secondary btn-sm" title="Close (Esc)" style="padding: 0.25rem 0.55rem; font-size: 0.85rem;">✕</button>
                </div>
            </div>

            <div class="smm-agent-chips">
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('What is the status of ')">📊 School Status</button>
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('Draft a warm email to ')">✉️ Draft Email</button>
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('Take a note for ')">📝 Take Note</button>
                <button type="button" class="smm-chip" onclick="window.smmFillPrompt('Schedule a meeting with ')">📅 Log Meeting</button>
                <button type="button" class="smm-chip" onclick="window.smmSendQuickPrompt('What meetings and follow-up tasks do I have scheduled?')">⏰ My Schedule</button>
            </div>

            <div id="smmAgentRefreshBanner" class="smm-agent-refresh-banner" style="display: none;">
                <span>✓ CRM records updated by Agent</span>
                <button type="button" onclick="window.location.reload()" class="btn btn-primary btn-sm" style="padding: 0.2rem 0.55rem; font-size: 0.72rem;">↻ Refresh View</button>
            </div>

            <div id="smmAgentMessages" class="smm-agent-messages"></div>

            <form id="smmAgentForm" class="smm-agent-input-bar" onsubmit="window.smmSubmitAgentMessage(event)">
                <textarea id="smmAgentInput" rows="2" placeholder="Ask anything: e.g. 'Log meeting with Paul at Poverest Primary on 18 Nov', 'Status of Gallions', 'Draft email to SENCO'..." onkeydown="if(event.key==='Enter' && !event.shiftKey){event.preventDefault(); window.smmSubmitAgentMessage(event);}"></textarea>
                <button type="submit" id="smmAgentSendBtn" class="btn btn-primary" style="align-self: flex-end; height: 38px; padding: 0 0.85rem;">Send &rarr;</button>
            </form>
        `;
        document.body.appendChild(drawer);

        renderStoredMessages();

        // Keyboard shortcut Ctrl+K / Cmd+K or Esc
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
            const sample = ctx.id
                ? `Try asking:<br>• <em>"Summarize the status and contacts for ${escapeHtml(ctx.name)}"</em><br>• <em>"Draft a short intro email to the Headteacher"</em><br>• <em>"Log a note: spoke to reception, follow up next Tuesday"</em>`
                : `I can execute tasks directly on your CRM:<br>• <strong>Status:</strong> <em>"What's the status of Poverest Primary?"</em><br>• <strong>Meetings:</strong> <em>"Log a meeting with Paul (Headteacher) at Poverest Primary on 2026-11-18 about SEN pupils"</em><br>• <strong>Notes:</strong> <em>"Take a note on Gallions Primary: SENCO interested in sandbox demo"</em><br>• <strong>Emails:</strong> <em>"Draft a follow-up email for Gallions Primary"</em>`;
            container.innerHTML = `
                <div class="smm-msg smm-msg-assistant">
                    <div class="smm-msg-bubble">${sample}</div>
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
                    ? `<a href="/seemymind/ui/schools/${escapeHtml(a.school_id)}" style="color: inherit; text-decoration: underline; margin-left: 0.25rem;">View &rarr;</a>`
                    : '';
                return `<div class="smm-action-pill">✓ ${escapeHtml(a.label)} ${link}</div>`;
            }).join('');

            const emailAction = actions.find(a => a.email_draft && a.email_draft.body);
            let copyBtn = '';
            if (emailAction) {
                const encoded = encodeURIComponent(`Subject: ${emailAction.email_draft.subject}\n\n${emailAction.email_draft.body}`);
                copyBtn = `<button type="button" class="btn btn-secondary btn-sm" style="margin-top: 0.35rem; font-size: 0.72rem;" onclick="navigator.clipboard.writeText(decodeURIComponent('${encoded}')); this.textContent='✓ Copied Email!'; setTimeout(()=>this.textContent='📋 Copy Subject & Body', 2000);">📋 Copy Subject & Body</button>`;
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
        if (ctx.id && prefix.endsWith(' ')) {
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

        // Show thinking indicator
        const thinkingEl = document.createElement('div');
        thinkingEl.className = 'smm-msg smm-msg-assistant';
        thinkingEl.innerHTML = `<div class="smm-msg-bubble" style="color: var(--soft); font-style: italic;">✨ Agent is working...</div>`;
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

            const reply = data.reply || 'Completed.';
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
            appendMessageDOM('assistant', '⚠️ Connection error while reaching the Agent endpoint.');
        } finally {
            sendBtn.disabled = false;
            inp.focus();
        }
    };

    document.addEventListener('DOMContentLoaded', initAgentUI);
})();
