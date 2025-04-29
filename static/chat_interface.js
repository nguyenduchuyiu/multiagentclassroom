// static/chat_interface.js
document.addEventListener('DOMContentLoaded', () => {
    console.log("chat_interface.js loaded");

    // --- DOM Elements ---
    const container = document.querySelector('.container');
    const chatbox = document.getElementById('chatMessages');
    const messageInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const participantsList = document.getElementById('participantsList');
    const messageCountEl = document.getElementById('messageCount');
    const problemDisplayEl = document.getElementById('problemDisplay');
    const connectionStatusIcon = document.getElementById('connectionStatusIcon');
    const statusText = document.getElementById('statusText');
    const restartBtn = document.getElementById('restartBtn');
    const exportBtn = document.getElementById('exportBtn');
    const currentStageEl = document.getElementById('currentStage');
    const stageDescriptionEl = document.getElementById('stageDescription');
    const progressFillEl = document.getElementById('progressFill');

    // --- State Variables ---
    let messageCounter = 0;
    let currentTypingAgents = new Set();
    let agentStatuses = {};
    let eventSource = null; // Initialize eventSource to null

    // --- Get session ID and username from HTML data attributes ---
    const currentSessionId = container?.dataset.sessionId;
    let currentUsername = container?.dataset.userName || '';

    // --- Check if essential data is present ---
    if (!currentSessionId) {
        console.error("CRITICAL: Session ID not found in HTML. Chat cannot function.");
        alert("Lỗi: Không tìm thấy ID phiên chat. Vui lòng quay lại trang danh sách và bắt đầu phiên mới.");
        // Optionally redirect: window.location.href = '/';
        return; // Stop script execution
    }

    // --- Functions ---

    function initializeUserDisplay() {
        if (!currentUsername) {
            // Fallback if username wasn't passed correctly
            currentUsername = localStorage.getItem(`chatcollab_username_${currentSessionId}`) || 'Bạn';
            console.warn("Username not found in data attribute, using fallback/localStorage.");
        }
        // Ensure username is trimmed
        currentUsername = currentUsername.trim();
        if (!currentUsername) currentUsername = 'Bạn'; // Final fallback

        console.log(`Username for session ${currentSessionId}: ${currentUsername}`);
        localStorage.setItem(`chatcollab_username_${currentSessionId}`, currentUsername);

        const userLi = participantsList?.querySelector('.user-participant');
        if (userLi) {
            const nameEl = userLi.querySelector('.participant-name');
            const avatarEl = userLi.querySelector('.participant-avatar');
            if (nameEl) nameEl.textContent = currentUsername;
            if (avatarEl) avatarEl.textContent = currentUsername.charAt(0).toUpperCase();
        } else {
            console.warn("User participant list item not found for display update.");
        }
    }

    function initializeAgentStatuses() {
        if (!participantsList) return;
        agentStatuses = {};
        currentTypingAgents.clear();
        participantsList.querySelectorAll('.agent-participant').forEach(div => {
            const agentName = div.dataset.agentName;
            if (agentName) agentStatuses[agentName] = 'idle';
        });
        updateParticipantDisplay();
    }

    function formatTimestamp(unixTimestamp) {
        try {
            const d = unixTimestamp ? new Date(parseInt(unixTimestamp, 10)) : new Date();
            if (isNaN(d.getTime())) throw new Error("Invalid date");
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
            return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
    }

    function escapeHTML(str) {
        const p = document.createElement('p');
        p.textContent = str || ''; // Ensure str is not null/undefined
        return p.innerHTML;
    }

    function renderMathInElement(el) {
        if (el && window.MathJax?.typesetPromise) {
            console.log("Typesetting MathJax for:", el); // Debug log
            MathJax.typesetPromise([el]).catch(err => console.error('MathJax typesetting error:', err));
        } else if (!el) {
            // console.warn("Attempted to render MathJax on a null element.");
        }
    }

    function displayMessage(eventData) {
        if (!chatbox) return;

        const msg = document.createElement('div');
        msg.classList.add('message');

        const senderId = eventData.source;
        const senderName = eventData.content?.sender_name || senderId;
        const text = eventData.content?.text || '(Nội dung trống)';
        const timestamp = eventData.timestamp;

        let senderType = 'ai';
        if (senderName === currentUsername) senderType = 'user';
        else if (senderId === 'System') senderType = 'system';

        let html = '';
        const timeStr = formatTimestamp(timestamp);

        if (senderType === 'user') {
            msg.classList.add('user-message');
        } else if (senderType === 'system') {
            msg.classList.add('system-message');
        } else {
            msg.classList.add('ai-message');
            const agentClass = `agent-${senderName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
            msg.classList.add(agentClass);
        }

        // Ensure senderName is escaped for display
        html = `
            <div class="message-header">
                <strong class="sender-name">${escapeHTML(senderName)}</strong>
                <span class="timestamp">${timeStr}</span>
            </div>
            <div class="message-content">
                <div class="message-text">${escapeHTML(text)}</div>
            </div>`;

        msg.innerHTML = html;
        chatbox.appendChild(msg);
        renderMathInElement(msg.querySelector('.message-text'));
        chatbox.scrollTop = chatbox.scrollHeight;

        messageCounter++;
        if (messageCountEl) messageCountEl.textContent = messageCounter;

        // Update stage display (optional)
        if (eventData.metadata?.phase_id && currentStageEl && stageDescriptionEl && progressFillEl) {
             const phaseId = parseInt(eventData.metadata.phase_id, 10);
             if (!isNaN(phaseId)) {
                 const phaseName = eventData.metadata.phase_name || `Giai đoạn ${phaseId}`;
                 const phaseDesc = eventData.metadata.phase_description || '';
                 currentStageEl.textContent = phaseName;
                 stageDescriptionEl.textContent = phaseDesc;
                 const progressPercent = (phaseId / 4) * 100; // Assuming 4 stages
                 progressFillEl.style.width = `${Math.min(100, Math.max(0, progressPercent))}%`;
             }
        }
    }

    function updateParticipantDisplay() {
        if (!typingIndicator || !participantsList) return;
        if (currentTypingAgents.size === 0) {
            typingIndicator.style.display = 'none';
        } else {
            typingIndicator.style.display = 'block';
            typingIndicator.innerHTML = `${[...currentTypingAgents].join(', ')} đang nhập...`;
        }

        Object.entries(agentStatuses).forEach(([agentName, status]) => {
            const div = participantsList.querySelector(`.participant[data-agent-name="${agentName}"]`);
            if (!div) return;
            const statusEl = div.querySelector('.participant-status');
            const dot = div.querySelector('.typing-dot');
            div.classList.remove('status-idle','status-typing','status-thinking');
            if (dot) dot.style.display = 'none';
            switch(status) {
                case 'typing':
                    div.classList.add('status-typing');
                    if (statusEl) statusEl.textContent = 'Đang nhập ';
                    if (dot) dot.style.display = 'inline-block';
                    break;
                case 'thinking':
                    div.classList.add('status-thinking');
                    if (statusEl) statusEl.textContent = 'Đang suy nghĩ...';
                    break;
                default: // idle
                    div.classList.add('status-idle');
                    if (statusEl) statusEl.textContent = 'Đang hoạt động';
            }
        });
    }

    function updateConnectionStatus(status) {
        const panel = document.querySelector('.status');
        if (!panel || !connectionStatusIcon || !statusText || !messageInput || !sendButton) return;
        panel.classList.remove('connecting','connected','disconnected');
        messageInput.disabled = true; // Disable input by default
        sendButton.disabled = true;

        switch(status) {
            case 'connected':
                connectionStatusIcon.style.color = 'var(--success-color)';
                statusText.textContent = 'Đã kết nối';
                panel.classList.add('connected');
                messageInput.disabled = false; // Enable input on connection
                sendButton.disabled = false;
                break;
            case 'disconnected':
                connectionStatusIcon.style.color = 'var(--error-color)';
                statusText.textContent = 'Mất kết nối';
                panel.classList.add('disconnected');
                break;
            default: // connecting
                connectionStatusIcon.style.color = 'var(--warning-color)';
                statusText.textContent = 'Đang kết nối...';
                panel.classList.add('connecting');
        }
    }

    function sendMessage() {
        if (!messageInput || !sendButton) return; // Check elements exist

        const text = messageInput.value.trim();
        if (!currentUsername) initializeUserDisplay(); // Make sure username is set
        if (!text || messageInput.disabled) return;

        messageInput.disabled = true;
        sendButton.disabled = true;

        const payload = { text, sender_name: currentUsername };
        fetch(`/send_message/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => {
            if (!res.ok) {
                console.error('Send error status:', res.status, res.statusText);
                // Try to get error message from response body
                return res.json().catch(() => ({ error: res.statusText })).then(errData => {
                    throw new Error(errData.error || 'Unknown error');
                });
            }
            // Success is handled by SSE echo
        })
        .catch(err => {
            console.error('Send error:', err);
            displayMessage({ source: 'System', content: { text: `Lỗi khi gửi tin nhắn: ${err.message || 'Lỗi không xác định'}`, sender_name: 'System' }, timestamp: Date.now() });
        })
        .finally(() => {
            // Re-enable only if connection is still open
            if (eventSource?.readyState === EventSource.OPEN) {
                if (messageInput) messageInput.disabled = false;
                if (sendButton) sendButton.disabled = false;
                if (messageInput) messageInput.focus();
            }
            if (messageInput) {
                messageInput.value = '';
                messageInput.style.height = 'auto';
            }
        });
    }

    // --- Event Listeners ---
    // Add null checks for elements
    sendButton?.addEventListener('click', sendMessage);
    messageInput?.addEventListener('keypress', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); sendMessage();
        }
    });
    messageInput?.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = `${messageInput.scrollHeight}px`;
    });
    restartBtn?.addEventListener('click', () => {
        if (confirm('Tải lại giao diện chat?')) window.location.reload();
    });
    exportBtn?.addEventListener('click', () => {
        if (!currentSessionId || !currentUsername) return;
        fetch(`/history/${currentSessionId}`)
            .then(r => {
                if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
                return r.json();
            })
            .then(history => {
                let content = `Chat Export - Session ${currentSessionId}\nUser: ${currentUsername}\n====================\n\n`;
                history.forEach(ev => {
                    const t = formatTimestamp(ev.timestamp);
                    const n = ev.content?.sender_name || ev.source;
                    content += `[${t}] ${escapeHTML(n)}: ${ev.content?.text || ''}\n`;
                });
                if (content.length <= 150) return alert('Không có nội dung để xuất.');
                const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = `chat-${currentUsername}-${currentSessionId.slice(0,8)}.txt`;
                document.body.appendChild(link);
                link.click();
                link.remove(); // Clean up the link element
                URL.revokeObjectURL(link.href); // Free up memory
            })
            .catch(err => {
                console.error("Export error:", err);
                alert('Không thể xuất chat.');
            });
    });

    // --- Server-Sent Events (SSE) Setup ---
    function connectSSE() {
        if (eventSource?.readyState === EventSource.OPEN) return; // Already open

        updateConnectionStatus('connecting');
        eventSource = new EventSource(`/stream/${currentSessionId}`);

        eventSource.onopen = () => {
            updateConnectionStatus('connected');
            initializeUserDisplay(); // Initialize user display info
            initializeAgentStatuses(); // Initialize agent display info
            renderMathInElement(problemDisplayEl); // Render problem math

            // Fetch initial chat history
            fetch(`/history/${currentSessionId}`)
                .then(r => {
                    if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
                    return r.json()
                })
                .then(history => {
                    if (chatbox) chatbox.innerHTML = '';
                    messageCounter = 0;
                    history.forEach(displayMessage); // displayMessage handles math rendering
                    if (messageInput) messageInput.focus();
                })
                .catch(err => {
                    console.error("History fetch error:", err);
                    displayMessage({ source: 'System', content: { text: 'Không thể tải lịch sử.', sender_name: 'System' }, timestamp: Date.now() })
                });
        };

        eventSource.onerror = err => {
            console.error('SSE error:', err);
            updateConnectionStatus('disconnected');
            if (eventSource) eventSource.close();
            if (statusText) statusText.textContent = 'Mất kết nối. Tải lại trang để thử.';
        };

        eventSource.addEventListener('new_message', e => {
            try { displayMessage(JSON.parse(e.data)); }
            catch (err) { console.error('Parsing new_message:', err, e.data); }
        });

        eventSource.addEventListener('agent_status', e => {
            try {
                const eventData = JSON.parse(e.data);
                const update = eventData.content; // Status data is inside content
                const { agent_name: name, status } = update;
                if (name && status && agentStatuses.hasOwnProperty(name)) {
                    agentStatuses[name] = status;
                    if (status === 'typing') currentTypingAgents.add(name);
                    else currentTypingAgents.delete(name);
                    updateParticipantDisplay();
                } else {
                    console.warn("Received invalid agent_status:", eventData);
                }
            } catch (err) { console.error('Parsing agent_status:', err, e.data); }
        });

        eventSource.addEventListener('message', e => { /* Handle keep-alive */ });

    } // End connectSSE

    // --- Initial Load ---
    connectSSE(); // Start connection

}); // End DOMContentLoaded