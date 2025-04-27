document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
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

    // --- State Variables ---
    let messageCounter = 0;
    let currentTypingAgents = new Set();
    let agentStatuses = {};
    let currentUsername = ''; // <<< Variable to store the user's name

    // --- Get and Store Username ---
    function initializeUser() {
        currentUsername = localStorage.getItem('chatcollab_username');
        if (!currentUsername) {
            currentUsername = prompt("Vui lòng nhập tên của bạn:", "Người dùng");
            if (!currentUsername) { // Handle empty prompt or cancel
                currentUsername = `Người dùng ${Math.floor(Math.random() * 1000)}`;
            }
            localStorage.setItem('chatcollab_username', currentUsername);
        }
        console.log(`Username set to: ${currentUsername}`);
        // Optional: Update the 'Bạn' entry in the participant list if desired
        const userParticipantName = participantsList.querySelector('.user-participant .participant-name');
        const userParticipantAvatar = participantsList.querySelector('.user-participant .participant-avatar');
         if(userParticipantName) userParticipantName.textContent = currentUsername; // Update name display
         if(userParticipantAvatar) userParticipantAvatar.textContent = currentUsername.charAt(0).toUpperCase(); // Update avatar initial
    }

    // --- Initialize Agent Statuses from HTML ---
    function initializeAgentStatuses() {
        agentStatuses = {};
        currentTypingAgents.clear();
        const participantDivs = participantsList.querySelectorAll('.participant[data-agent-name]');
        participantDivs.forEach(div => {
            const agentName = div.dataset.agentName;
            // Initialize only non-Human agents AND not the current user's name
            // NOTE: Assumes user name won't clash with agent names from config
            if (agentName && agentName !== 'Human' && agentName !== currentUsername) {
                agentStatuses[agentName] = 'idle';
            }
        });
        updateParticipantDisplay();
    }

    // --- Utility Functions (formatTimestamp, escapeHTML - remain the same) ---
    function formatTimestamp(ts) { // Keep existing
        if (!ts) return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        try {
            const d = new Date(ts);
            if (isNaN(d.getTime())) {
                 console.warn("Invalid timestamp received:", ts);
                 return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            }
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            console.error("Error formatting timestamp:", ts, e);
            return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
    }

    function escapeHTML(str) { // Keep existing
        if (typeof str !== 'string') return '';
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }


    // --- Display Message Function (MODIFIED) ---
    function displayMessage(messageData) {
        const msg = document.createElement('div');
        msg.classList.add('message');

        const sender = messageData.sender; // This is now the username, 'System', or agent_id
        const senderName = messageData.sender_name || sender; // Use agent_name if available, else sender (username, System, agent_id)
        const text = messageData.text;
        const timestamp = messageData.timestamp;

        let senderType = 'ai'; // Default assumption

        // <<< Check if the sender matches the current user's name OR is the old "Human" value >>>
        if (sender === currentUsername || sender === 'Human') {
            senderType = 'user';
        } else if (sender === 'System') {
            senderType = 'system';
        }
        // else: It's an agent

        let html = '';
        if (senderType === 'user') {
            msg.classList.add('user-message');
            // Display "Bạn" consistently, even though the saved sender is the username
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
                    <strong class="sender-name">${escapeHTML(senderName)}</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content system-content">
                    <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        } else { // AI Agent message
            msg.classList.add('ai-message');
             if (senderName) { // Use agent_name for class if available
                 const agentClass = `agent-${senderName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
                 msg.classList.add(agentClass);
             }
            html = `
                <div class="message-header">
                    <strong class="sender-name">${escapeHTML(senderName)}</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content">
                    <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        }

        msg.innerHTML = html;
        chatbox.appendChild(msg);
        chatbox.scrollTop = chatbox.scrollHeight;

        // Update message counter
        messageCounter++;
        messageCountEl.textContent = messageCounter;

        // Optional: MathJax
        if (window.MathJax && MathJax.typesetPromise) {
            MathJax.typesetPromise([msg]).catch(err => console.error('MathJax error:', err));
        }
    }

    // --- Update Participant Panel UI (No changes needed here, it works by agent name) ---
    function updateParticipantDisplay() { // Keep existing
        if (currentTypingAgents.size === 0) {
            typingIndicator.style.display = 'none';
            typingIndicator.innerHTML = '';
        } else {
            const names = Array.from(currentTypingAgents).join(', ');
            typingIndicator.innerHTML = `${escapeHTML(names)} đang nhập...`;
            typingIndicator.style.display = 'block';
        }
        for (const agentName in agentStatuses) {
            const participantDiv = participantsList.querySelector(`.participant[data-agent-name="${agentName}"]`);
            if (!participantDiv) continue;
            const statusEl = participantDiv.querySelector('.participant-status');
            const dot = participantDiv.querySelector('.typing-dot');
            const status = agentStatuses[agentName] || 'idle';
            participantDiv.classList.remove('status-idle', 'status-typing', 'status-thinking');
            if (dot) dot.style.display = 'none';
            switch (status) {
                case 'typing':
                    if (statusEl) statusEl.textContent = 'Đang nhập ';
                    if (dot) dot.style.display = 'inline-block';
                    participantDiv.classList.add('status-typing');
                    break;
                case 'thinking':
                    if (statusEl) statusEl.textContent = 'Đang suy nghĩ...';
                    participantDiv.classList.add('status-thinking');
                    break;
                case 'idle':
                default:
                    if (statusEl) statusEl.textContent = 'Đang hoạt động';
                    participantDiv.classList.add('status-idle');
                    break;
            }
        }
    }

    // --- Update Connection Status Bar (Keep existing) ---
    function updateConnectionStatus(status) { // Keep existing
        const panel = document.querySelector('.status');
        if (!panel) return;
        panel.classList.remove('connecting', 'connected', 'disconnected');
        messageInput.disabled = true;
        sendButton.disabled = true;
        sendButton.classList.add('disabled');
        switch (status) {
            case 'connected':
                connectionStatusIcon.style.color = 'var(--success-color)';
                statusText.textContent = 'Đã kết nối';
                panel.classList.add('connected');
                messageInput.disabled = false;
                sendButton.disabled = false;
                sendButton.classList.remove('disabled');
                break;
            case 'disconnected':
                connectionStatusIcon.style.color = 'var(--error-color)';
                statusText.textContent = 'Mất kết nối';
                panel.classList.add('disconnected');
                break;
            case 'connecting':
            default:
                connectionStatusIcon.style.color = 'var(--warning-color)';
                statusText.textContent = 'Đang kết nối...';
                panel.classList.add('connecting');
                break;
        }
    }

    // --- Send Message Logic (MODIFIED) ---
    function sendMessage() {
        const text = messageInput.value.trim();
        // <<< Ensure username is initialized before sending >>>
        if (!currentUsername) {
            initializeUser(); // Make sure we have a username
            if (!currentUsername) { // Still no username? Abort.
                 alert("Không thể lấy tên người dùng. Không thể gửi tin nhắn.");
                 return;
            }
        }

        if (!text || messageInput.disabled) return;

        messageInput.disabled = true;
        sendButton.disabled = true;
        sendButton.classList.add('disabled');

        // <<< Include sender_name in the payload >>>
        const payload = {
            text: text,
            sender_name: currentUsername
        };

        fetch('/send_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload) // Send the payload with username
        })
        .then(res => {
            if (!res.ok) {
                 console.error("Error sending message:", res.status, res.statusText);
                 displayMessage({
                     sender: 'System',
                     text: `Lỗi gửi tin nhắn: ${res.statusText}`,
                     timestamp: Date.now(),
                     sender_name: 'System'
                 });
            }
            // Message display will happen via SSE echo
        })
        .catch(err => {
            console.error("Network error sending message:", err);
            displayMessage({
                 sender: 'System',
                 text: `Lỗi mạng khi gửi: ${err.message}`,
                 timestamp: Date.now(),
                 sender_name: 'System'
            });
        })
        .finally(() => {
             if (eventSource && eventSource.readyState === EventSource.OPEN) {
                messageInput.disabled = false;
                sendButton.disabled = false;
                sendButton.classList.remove('disabled');
                messageInput.focus();
             }
             messageInput.value = '';
             messageInput.style.height = 'auto';
        });
    }

    // --- Event Listeners for Sending (Keep existing) ---
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = `${messageInput.scrollHeight}px`;
    });

    // --- Server-Sent Events (SSE) Setup (MODIFIED History Fetch) ---
    let eventSource;
    function connectSSE() {
        if (eventSource && (eventSource.readyState === EventSource.OPEN || eventSource.readyState === EventSource.CONNECTING)) {
            return;
        }

        updateConnectionStatus('connecting');
        eventSource = new EventSource('/stream');

        eventSource.onopen = () => {
            console.log("SSE connection established.");
            updateConnectionStatus('connected');
            // <<< Initialize user *before* initializing agent statuses and fetching history >>>
            initializeUser();
            initializeAgentStatuses(); // Reset statuses based on current participants

            // Fetch initial chat history
            fetch('/history')
                .then(response => {
                    if (!response.ok) throw new Error(`History fetch failed: ${response.statusText}`);
                    return response.json();
                })
                .then(history => {
                    chatbox.innerHTML = '';
                    messageCounter = 0;
                    // <<< Use the modified displayMessage which handles username vs 'Human' >>>
                    history.forEach(msg => displayMessage(msg));
                    messageInput.focus();
                })
                .catch(error => {
                    console.error('Error fetching history:', error);
                     displayMessage({ sender: 'System', text: 'Không thể tải lịch sử chat.', timestamp: Date.now(), sender_name:'System' });
                });
        };

        eventSource.onerror = (err) => { // Keep existing error handling
            console.error("SSE error:", err);
            updateConnectionStatus('disconnected');
            eventSource.close();
            setTimeout(connectSSE, 5000);
        };

        // Event listeners for 'new_message' and 'agent_status' remain the same
        // as displayMessage and updateParticipantDisplay handle the logic now.
        eventSource.addEventListener('new_message', e => {
            try {
                const messageData = JSON.parse(e.data);
                displayMessage(messageData); // Handles user vs agent logic
            } catch (error) {
                console.error("Error parsing new_message data:", error, e.data);
            }
        });

        eventSource.addEventListener('agent_status', e => { // Keep existing
            try {
                const statusUpdate = JSON.parse(e.data);
                const agentName = statusUpdate.agent_name;
                const status = statusUpdate.status;
                if (!agentName) return;
                agentStatuses[agentName] = status;
                if (status === 'typing') {
                    currentTypingAgents.add(agentName);
                } else {
                    currentTypingAgents.delete(agentName);
                }
                updateParticipantDisplay();
            } catch (error) {
                console.error("Error parsing agent_status data:", error, e.data);
            }
        });

         eventSource.addEventListener('message', function(event) { // Keep existing keep-alive
              if (event.data && event.data.includes("keep-alive")) { }
              else if (event.data) { }
         });

    } // End connectSSE

    // --- Control Buttons (Restart, Export - Keep existing) ---
    restartBtn.addEventListener('click', () => { // Keep existing
        if (confirm('Bạn có chắc muốn bắt đầu lại cuộc trò chuyện? Thao tác này sẽ xóa lịch sử hiện tại.')) {
            console.log("Restarting chat...");
            chatbox.innerHTML = '';
            messageCounter = 0;
            messageCountEl.textContent = '0';
            if (turnCountEl) turnCountEl.textContent = '0';
            initializeAgentStatuses();
            if (eventSource) eventSource.close();
            // Don't clear username from localStorage on restart
            setTimeout(connectSSE, 500);
        }
    });

    exportBtn.addEventListener('click', () => { // Keep existing
        let content = 'ChatCollab Export\n====================\n\n';
        chatbox.querySelectorAll('.message').forEach(msgElement => {
            const nameEl = msgElement.querySelector('.sender-name');
            // <<< Use the displayed name ("Bạn" or Agent Name) for export >>>
            const name = nameEl ? nameEl.textContent.trim() : 'Unknown Sender';
            const textEl = msgElement.querySelector('.message-text');
            const timeEl = msgElement.querySelector('.timestamp');
            const text = textEl ? textEl.textContent.trim() : '';
            const time = timeEl ? timeEl.textContent.trim() : '';
            content += `[${time}] ${name}: ${text}\n`;
        });
        if (content.length <= 30) return alert('Không có nội dung để xuất.');
        try {
            const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            const dateStr = new Date().toISOString().slice(0, 10);
            link.download = `chat-export-${dateStr}.txt`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(link.href);
        } catch (error) {
             console.error("Error creating export blob/link:", error);
             alert("Đã xảy ra lỗi khi tạo file xuất.");
        }
    });

    // --- Initial Load ---
    connectSSE(); // Start connection, which will then call initializeUser

}); // End DOMContentLoaded