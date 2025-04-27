document.addEventListener('DOMContentLoaded', () => {
    // Lấy các phần tử DOM quan trọng
    const chatbox = document.getElementById('chatMessages');
    const messageInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const participantsList = document.getElementById('participantsList');
    const messageCountEl = document.getElementById('messageCount');
    const turnCountEl = document.getElementById('turnCount');
    const connectionStatusIcon = document.getElementById('connectionStatusIcon');
    const statusText = document.getElementById('statusText');
    const restartBtn = document.getElementById('restartBtn');
    const exportBtn = document.getElementById('exportBtn');

    let messageCounter = 0;
    let currentTypingAgents = new Set();               // Quản lý chỉ báo chung
    let agentStatuses = {};                             // Lưu trạng thái từng agent

    // --- Khởi tạo trạng thái ban đầu cho các agent ---
    function initializeAgentStatuses() {
        agentStatuses = {};
        const divs = participantsList.querySelectorAll('.participant[data-agent-id]');
        divs.forEach(div => {
            const id = div.dataset.agentId;
            if (id && id !== 'Human') agentStatuses[id] = 'idle';
        });
        updateParticipantDisplay();
    }

    // --- Tiện ích chung ---
    function formatTimestamp(ts) {
        if (!ts) return '';
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function escapeHTML(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // --- Hiển thị tin nhắn ---
    function displayMessage(sender, text, timestamp, senderType = 'ai', agentId = null) {
        const msg = document.createElement('div');
        msg.classList.add('message');

        let html = '';
        if (senderType === 'user') {
            msg.classList.add('user-message');
            html = `
                <div class="message-header">
                    <strong class="sender-name">Bạn</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content">
                    <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        } else if (senderType === 'system') {
            msg.classList.add('system-message');
            html = `
                <div class="message-header">
                    <strong class="sender-name">${sender}</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content system-content">
                    <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        } else {
            msg.classList.add('ai-message');
            if (agentId) {
                msg.classList.add(`sender-${agentId.toLowerCase()}`);
            }
            html = `
                <div class="message-header">
                    <strong class="sender-name">${sender}</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content">
                    <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        }

        msg.innerHTML = html;
        chatbox.appendChild(msg);
        chatbox.scrollTop = chatbox.scrollHeight;

        messageCounter++;
        messageCountEl.textContent = messageCounter;

        if (window.MathJax && MathJax.typesetPromise) {
            MathJax.typesetPromise([msg]).catch(err => console.error('MathJax error:', err));
        }
    }

    // --- Cập nhật hiển thị panel người tham gia ---
    function updateParticipantDisplay() {
        // Typing chung
        if (currentTypingAgents.size === 0) {
            typingIndicator.style.display = 'none';
            typingIndicator.innerHTML = '';
        } else {
            const names = Array.from(currentTypingAgents).map(id => {
                const d = participantsList.querySelector(`.participant[data-agent-id="${id}"]`);
                return d?.querySelector('.participant-name')?.textContent || id;
            }).join(', ');
            typingIndicator.innerHTML = `${names} đang nhập...`;
            typingIndicator.style.display = 'block';
        }

        // Trạng thái từng agent
        const divs = participantsList.querySelectorAll('.participant[data-agent-id]');
        divs.forEach(div => {
            const id = div.dataset.agentId;
            if (id === 'Human') return;
            const statusEl = div.querySelector(`#status-${id}`);
            const dot = div.querySelector('.typing-dot');
            const st = agentStatuses[id] || 'idle';
            div.classList.remove('status-idle', 'status-typing', 'status-thinking');
            if (st === 'typing') {
                statusEl.textContent = 'Typing ';
                dot && (dot.style.display = 'inline-block');
                div.classList.add('status-typing');
            } else if (st === 'thinking') {
                statusEl.textContent = 'Thinking...';
                dot && (dot.style.display = 'none');
                div.classList.add('status-thinking');
            } else {
                statusEl.textContent = 'Đang hoạt động ';
                dot && (dot.style.display = 'none');
                div.classList.add('status-idle');
            }
        });
    }

    // --- Cập nhật trạng thái kết nối ---
    function updateConnectionStatus(status) {
        const panel = document.querySelector('.status');
        panel.classList.remove('connecting', 'connected', 'disconnected');
        switch (status) {
            case 'connected':
                connectionStatusIcon.style.color = 'var(--success-color)';
                statusText.textContent = 'Đã kết nối';
                panel.classList.add('connected');
                messageInput.disabled = false;
                sendButton.disabled = false;
                break;
            case 'disconnected':
                connectionStatusIcon.style.color = 'var(--error-color)';
                statusText.textContent = 'Mất kết nối';
                panel.classList.add('disconnected');
                messageInput.disabled = true;
                sendButton.disabled = true;
                break;
            default:
                connectionStatusIcon.style.color = 'var(--warning-color)';
                statusText.textContent = 'Đang kết nối...';
                panel.classList.add('connecting');
                messageInput.disabled = true;
                sendButton.disabled = true;
        }
    }

    // --- Gửi tin nhắn ---
    function sendMessage() {
        const text = messageInput.value.trim();
        if (!text || messageInput.disabled) return;

        messageInput.disabled = true;
        sendButton.disabled = true;
        sendButton.classList.add('disabled');

        fetch('/send_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        })
        .then(res => {
            if (!res.ok) {
                displayMessage('System', `Lỗi gửi: ${res.statusText}`, Date.now(), 'system');
            }
        })
        .catch(err => displayMessage('System', `Lỗi mạng: ${err.message}`, Date.now(), 'system'))
        .finally(() => {
            if (eventSource && eventSource.readyState === EventSource.OPEN) {
                messageInput.disabled = false;
                sendButton.disabled = false;
                sendButton.classList.remove('disabled');
                messageInput.focus();
            }
        });

        messageInput.value = '';
        messageInput.style.height = 'auto';
    }

    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); sendMessage();
        }
    });
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = `${messageInput.scrollHeight}px`;
    });

    // --- Thiết lập SSE ---
    let eventSource;
    function connectSSE() {
        if (eventSource &&
            (eventSource.readyState === EventSource.OPEN || eventSource.readyState === EventSource.CONNECTING)) return;

        updateConnectionStatus('connecting');
        eventSource = new EventSource('/stream');

        eventSource.onopen = () => {
            updateConnectionStatus('connected');
            initializeAgentStatuses();
            fetch('/history')
                .then(r => r.json())
                .then(history => {
                    chatbox.innerHTML = '';
                    messageCounter = 0;
                    history.forEach(msg => {
                        const type = msg.sender === 'Human' ? 'user' :
                                     (msg.sender === 'System' ? 'system' : 'ai');
                        const aid = type === 'ai' ? msg.sender : null;
                        displayMessage(msg.sender, msg.text, msg.timestamp, type, aid);
                    });
                    messageInput.focus();
                });
        };

        eventSource.onerror = err => {
            updateConnectionStatus('disconnected');
            eventSource.close();
            setTimeout(connectSSE, 5000);
        };

        eventSource.addEventListener('new_message', e => {
            try {
                const m = JSON.parse(e.data);
                const type = m.sender === 'Human' ? 'user' :
                             (m.sender === 'System' ? 'system' : 'ai');
                const aid = type === 'ai' ? m.sender : null;
                displayMessage(m.sender, m.text, m.timestamp, type, aid);
            } catch (e) { console.error(e); }
        });

        eventSource.addEventListener('agent_status', e => {
            try {
                const upd = JSON.parse(e.data);
                const id = upd.agent_id;
                const st = upd.status;  // 'typing', 'thinking', 'idle'
                agentStatuses[id] = st;
                if (st === 'typing') currentTypingAgents.add(id);
                else currentTypingAgents.delete(id);
                updateParticipantDisplay();
            } catch (e) { console.error(e); }
        });
    }

    // --- Nút Restart ---
    restartBtn.addEventListener('click', () => {
        if (confirm('Bạn có chắc muốn bắt đầu lại cuộc trò chuyện?')) {
            chatbox.innerHTML = '';
            messageCounter = 0;
            messageCountEl.textContent = '0';
            turnCountEl.textContent = '0';
            currentTypingAgents.clear();
            initializeAgentStatuses();
            if (eventSource) eventSource.close();
            setTimeout(connectSSE, 500);
        }
    });

    // --- Nút Export ---
    exportBtn.addEventListener('click', () => {
        let content = '';
        chatbox.querySelectorAll('.message').forEach(msg => {
            const name = msg.querySelector('.sender-name')?.textContent || '';
            const txt = msg.querySelector('.message-text')?.textContent || '';
            const time = msg.querySelector('.timestamp')?.textContent || '';
            content += `[${time}] ${name}: ${txt}\n`;
        });
        if (!content) return alert('Không có nội dung để xuất.');
        const blob = new Blob([content], { type: 'text/plain' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `chat_export_${new Date().toISOString().slice(0,10)}.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    });

    // --- Khởi tạo ---
    connectSSE();
});
