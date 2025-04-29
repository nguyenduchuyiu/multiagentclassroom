// static/script.js
document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const chatbox = document.getElementById('chatMessages');
    const messageInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const participantsList = document.getElementById('participantsList');
    const messageCountEl = document.getElementById('messageCount');
    const problemDisplayEl = document.getElementById('problemDisplay'); //

    // const turnCountEl = document.getElementById('turnCount'); // Optional
    const connectionStatusIcon = document.getElementById('connectionStatusIcon');
    const statusText = document.getElementById('statusText');
    const restartBtn = document.getElementById('restartBtn');
    const exportBtn = document.getElementById('exportBtn');
    // Stage display elements (optional)
    const currentStageEl = document.getElementById('currentStage');
    const stageDescriptionEl = document.getElementById('stageDescription');
    const progressFillEl = document.getElementById('progressFill');


    // --- State Variables ---
    let messageCounter = 0;
    let currentTypingAgents = new Set();
    let agentStatuses = {}; // Stores status by agent *name*
    let currentUsername = ''; // Stores the user's name

    // --- Get and Store Username ---
    function initializeUser() {
        currentUsername = localStorage.getItem('chatcollab_username');
        if (!currentUsername) {
            currentUsername = prompt("Vui lòng nhập tên của bạn:", "Bạn"); // Default to "Bạn"
            if (!currentUsername || currentUsername.trim() === "") { // Handle empty prompt or cancel
                currentUsername = `Người dùng ${Math.floor(Math.random() * 1000)}`;
            }
            localStorage.setItem('chatcollab_username', currentUsername.trim());
            currentUsername = currentUsername.trim(); // Ensure trimmed version is used
        }
        console.log(`Username set to: ${currentUsername}`);
        // Update the static 'Bạn' entry in the participant list
        const userParticipantLi = participantsList.querySelector('.user-participant');
        if (userParticipantLi) {
            const userParticipantName = userParticipantLi.querySelector('.participant-name');
            const userParticipantAvatar = userParticipantLi.querySelector('.participant-avatar');
            if(userParticipantName) userParticipantName.textContent = currentUsername;
            if(userParticipantAvatar) userParticipantAvatar.textContent = currentUsername.charAt(0).toUpperCase();
        }
    }

    // --- Initialize Agent Statuses from HTML ---
    function initializeAgentStatuses() {
        agentStatuses = {};
        currentTypingAgents.clear();
        // Select only agent participants (exclude user-participant)
        const participantDivs = participantsList.querySelectorAll('.agent-participant');
        participantDivs.forEach(div => {
            const agentName = div.dataset.agentName; // Get name from data attribute
            if (agentName) {
                agentStatuses[agentName] = 'idle'; // Initialize all agents as idle
            }
        });
        updateParticipantDisplay(); // Update UI based on initial idle state
    }

    // --- Utility Functions ---
    function formatTimestamp(unixTimestamp) {
        if (!unixTimestamp) return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        try {
            // Assuming timestamp is in milliseconds from backend
            const d = new Date(parseInt(unixTimestamp, 10));
            if (isNaN(d.getTime())) {
                 console.warn("Invalid timestamp received:", unixTimestamp);
                 return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            }
            return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            console.error("Error formatting timestamp:", unixTimestamp, e);
            return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
    }

    function escapeHTML(str) {
        if (typeof str !== 'string') return '';
        const p = document.createElement('p');
        p.textContent = str;
        return p.innerHTML;
    }

    // --- Render Math using MathJax ---
    function renderMathInElement(element) {
        if (element && window.MathJax && MathJax.typesetPromise) { // Check if element exists
            console.log("Typesetting MathJax for:", element); // Debug log
            MathJax.typesetPromise([element]).catch(err => console.error('MathJax typesetting error:', err));
        } else if (!element) {
            console.warn("Attempted to render MathJax on a null element.");
        }
    }

    // --- Display Message Function (MODIFIED) ---
    function displayMessage(eventData) {
        // eventData structure: { event_id, timestamp, event_type, source, content: { text, sender_name }, metadata }
        const msg = document.createElement('div');
        msg.classList.add('message');

        // Use sender_name for display, source for identification if needed
        const senderId = eventData.source; // e.g., user-khai, agent-uuid, System
        const senderName = eventData.content?.sender_name || senderId; // Use provided name, fallback to ID
        const text = eventData.content?.text || '(Nội dung trống)';
        const timestamp = eventData.timestamp;

        let senderType = 'ai'; // Default assumption

        // <<< Identify user message by checking if senderName matches currentUsername >>>
        if (senderName === currentUsername) {
            senderType = 'user';
        } else if (senderId === 'System') { // Identify system messages by source ID
            senderType = 'system';
        }
        // else: It's an AI agent message

        let html = '';
        if (senderType === 'user') {
            msg.classList.add('user-message');
            // Display the actual username now
            html = `
                <div class="message-header">
                    <strong class="sender-name">${escapeHTML(senderName)}</strong>
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
             // Add agent-specific class using the agent's name for styling
             const agentClass = `agent-${senderName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
             msg.classList.add(agentClass);
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

        // Render MathJax for the new message content
        const messageTextElement = msg.querySelector('.message-text');
        renderMathInElement(messageTextElement);

        chatbox.scrollTop = chatbox.scrollHeight;

        // Update message counter
        messageCounter++;
        if (messageCountEl) messageCountEl.textContent = messageCounter;

        // Update stage display based on metadata if available
        if (eventData.metadata?.phase_id && currentStageEl && stageDescriptionEl && progressFillEl) {
             const phaseId = eventData.metadata.phase_id;
             const phaseName = eventData.metadata.phase_name || `Giai đoạn ${phaseId}`; // Fallback name
             const phaseDesc = eventData.metadata.phase_description || '';
             currentStageEl.textContent = phaseName;
             stageDescriptionEl.textContent = phaseDesc;
             // Update progress bar (example: assuming 4 stages)
             const progressPercent = (parseInt(phaseId, 10) / 4) * 100;
             progressFillEl.style.width = `${Math.min(100, Math.max(0, progressPercent))}%`;
        }
    }

    // --- Update Participant Panel UI ---
    function updateParticipantDisplay() {
        // Update general typing indicator
        if (currentTypingAgents.size === 0) {
            typingIndicator.style.display = 'none';
            typingIndicator.innerHTML = '';
        } else {
            const names = Array.from(currentTypingAgents).join(', ');
            typingIndicator.innerHTML = `${escapeHTML(names)} đang nhập...`;
            typingIndicator.style.display = 'block';
        }

        // Update individual agent statuses
        for (const agentName in agentStatuses) {
            // Find participant LI using the data-agent-name attribute
            const participantDiv = participantsList.querySelector(`.participant[data-agent-name="${agentName}"]`);
            if (!participantDiv) continue; // Skip if participant not found (e.g., user)

            const statusEl = participantDiv.querySelector('.participant-status');
            const dot = participantDiv.querySelector('.typing-dot');
            const status = agentStatuses[agentName] || 'idle';

            participantDiv.classList.remove('status-idle', 'status-typing', 'status-thinking');
            if (dot) dot.style.display = 'none'; // Hide dot by default

            switch (status) {
                case 'typing':
                    if (statusEl) statusEl.textContent = 'Đang nhập '; // Space for dot
                    if (dot) dot.style.display = 'inline-block'; // Show dot
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

    // --- Update Connection Status Bar ---
    function updateConnectionStatus(status) {
        const panel = document.querySelector('.status');
        if (!panel) return;
        panel.classList.remove('connecting', 'connected', 'disconnected');
        messageInput.disabled = true; // Disable input by default
        sendButton.disabled = true;
        sendButton.classList.add('disabled');

        switch (status) {
            case 'connected':
                connectionStatusIcon.style.color = 'var(--success-color)';
                statusText.textContent = 'Đã kết nối';
                panel.classList.add('connected');
                messageInput.disabled = false; // Enable input on connection
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
        // Ensure username is initialized before sending
        if (!currentUsername) {
            initializeUser();
            if (!currentUsername) {
                alert("Không thể lấy tên người dùng. Vui lòng tải lại trang và nhập tên.");
                return;
            }
        }

        if (!text || messageInput.disabled) return;

        messageInput.disabled = true;
        sendButton.disabled = true;
        sendButton.classList.add('disabled');

        // Include sender_name in the payload
        const payload = {
            text: text,
            sender_name: currentUsername // Send the user's actual name
        };

        fetch('/send_message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(res => {
            if (!res.ok) {
                 // Display error message in chat
                 res.json().then(errData => {
                     const errorMsg = errData.error || res.statusText;
                     console.error("Error sending message:", res.status, errorMsg);
                     displayMessage({
                         source: 'System', // Use System ID
                         content: { text: `Lỗi gửi tin nhắn: ${errorMsg}`, sender_name: 'System' },
                         timestamp: Date.now(),
                         event_type: 'system_message'
                     });
                 }).catch(() => { // Handle cases where JSON parsing fails
                     console.error("Error sending message:", res.status, res.statusText);
                      displayMessage({
                         source: 'System',
                         content: { text: `Lỗi gửi tin nhắn: ${res.statusText}`, sender_name: 'System' },
                         timestamp: Date.now(),
                         event_type: 'system_message'
                     });
                 });
            }
            // Success: Message display will happen via SSE echo from the server
        })
        .catch(err => {
            console.error("Network error sending message:", err);
            displayMessage({
                 source: 'System',
                 content: { text: `Lỗi mạng khi gửi: ${err.message}`, sender_name: 'System' },
                 timestamp: Date.now(),
                 event_type: 'system_message'
            });
        })
        .finally(() => {
             // Re-enable input only if connection is still active
             if (eventSource && eventSource.readyState === EventSource.OPEN) {
                messageInput.disabled = false;
                sendButton.disabled = false;
                sendButton.classList.remove('disabled');
                messageInput.focus();
             }
             messageInput.value = ''; // Clear input field
             messageInput.style.height = 'auto'; // Reset height
        });
    }

    // --- Event Listeners for Sending ---
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); // Prevent newline
            sendMessage();
        }
    });
    // Auto-resize textarea
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto'; // Reset height
        messageInput.style.height = `${messageInput.scrollHeight}px`; // Set to scroll height
    });

    // --- Server-Sent Events (SSE) Setup ---
    let eventSource;
    function connectSSE() {
        if (eventSource && (eventSource.readyState === EventSource.OPEN || eventSource.readyState === EventSource.CONNECTING)) {
            console.log("SSE connection already open or connecting.");
            return;
        }

        updateConnectionStatus('connecting');
        eventSource = new EventSource('/stream'); // Connect to the backend stream

        eventSource.onopen = () => {
            console.log("SSE connection established.");
            updateConnectionStatus('connected');
            // Get username FIRST
            initializeUser();
            // Reset agent statuses based on HTML participant list (which excludes user)
            initializeAgentStatuses();

            // <<< Render MathJax for the initial problem description >>>
            renderMathInElement(problemDisplayEl);

            // Fetch initial chat history AFTER connection and user init
            fetch('/history')
                .then(response => {
                    if (!response.ok) throw new Error(`History fetch failed: ${response.statusText}`);
                    return response.json();
                })
                .then(history => {
                    chatbox.innerHTML = ''; // Clear existing messages
                    messageCounter = 0;
                    // Display history using the updated displayMessage function
                    history.forEach(eventData => displayMessage(eventData));
                    messageInput.focus();
                })
                .catch(error => {
                    console.error('Error fetching history:', error);
                     displayMessage({
                         source: 'System',
                         content: { text: 'Không thể tải lịch sử chat.', sender_name: 'System'},
                         timestamp: Date.now(),
                         event_type: 'system_message'
                        });
                });
        };

        eventSource.onerror = (err) => {
            console.error("SSE error:", err);
            updateConnectionStatus('disconnected');
            eventSource.close();
            // Attempt to reconnect after a delay
            setTimeout(connectSSE, 5000);
        };

        // Listen for 'new_message' events from the server
        eventSource.addEventListener('new_message', e => {
            try {
                // The backend now sends the full event structure in the 'data' field
                const eventData = JSON.parse(e.data);
                displayMessage(eventData); // Display the message
            } catch (error) {
                console.error("Error parsing new_message data:", error, e.data);
            }
        });

        // Listen for 'agent_status' events
        eventSource.addEventListener('agent_status', e => {
            try {
                // Backend sends { agent_id, status, agent_name } inside 'data'
                const statusUpdate = JSON.parse(e.data);
                // Use agent_name to update status map and UI
                const agentName = statusUpdate.content?.agent_name;
                const status = statusUpdate.content?.status;

                if (!agentName || !status) {
                    console.warn("Received incomplete agent_status update:", statusUpdate);
                    return;
                }

                agentStatuses[agentName] = status; // Update status map

                // Update the set of currently typing agents
                if (status === 'typing') {
                    currentTypingAgents.add(agentName);
                } else {
                    currentTypingAgents.delete(agentName);
                }
                updateParticipantDisplay(); // Refresh the UI
            } catch (error) {
                console.error("Error parsing agent_status data:", error, e.data);
            }
        });

         // Generic message handler for keep-alive or other messages
         eventSource.addEventListener('message', function(event) {
              // console.log("Generic SSE message:", event.data); // Optional: log keep-alive
         });

    } // End connectSSE

    // --- Control Buttons (Restart, Export) ---
    restartBtn.addEventListener('click', () => {
        if (confirm('Bạn có chắc muốn bắt đầu lại cuộc trò chuyện? Thao tác này sẽ xóa lịch sử hiện tại trên trình duyệt.')) {
            console.log("Restarting chat...");
            chatbox.innerHTML = ''; // Clear messages
            messageCounter = 0;
            if(messageCountEl) messageCountEl.textContent = '0';
            // if(turnCountEl) turnCountEl.textContent = '0'; // Reset turn count if used

            // Re-initialize user (in case they want to change name implicitly, though we don't prompt again here)
            initializeUser();
            // Reset agent statuses based on HTML
            initializeAgentStatuses();

            // Close existing connection and reconnect
            if (eventSource) eventSource.close();
            setTimeout(connectSSE, 500); // Reconnect after a short delay
        }
    });

    exportBtn.addEventListener('click', () => {
        let content = `ChatCollab Export - ${new Date().toLocaleString()}\n`;
        content += `User: ${currentUsername}\n`;
        content += '====================\n\n';

        // Fetch history again for a complete export (or use stored history if available)
        fetch('/history')
            .then(response => response.json())
            .then(history => {
                history.forEach(eventData => {
                    const senderName = eventData.content?.sender_name || eventData.source;
                    const text = eventData.content?.text || '';
                    const time = formatTimestamp(eventData.timestamp);
                    content += `[${time}] ${escapeHTML(senderName)}: ${text}\n`;
                });

                if (content.length <= 100) return alert('Không có nội dung để xuất.'); // Adjust check

                try {
                    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    const dateStr = new Date().toISOString().slice(0, 10);
                    link.download = `chat-export-${currentUsername}-${dateStr}.txt`;
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);
                    URL.revokeObjectURL(link.href);
                } catch (error) {
                     console.error("Error creating export blob/link:", error);
                     alert("Đã xảy ra lỗi khi tạo file xuất.");
                }
            })
            .catch(error => {
                console.error("Error fetching history for export:", error);
                alert("Không thể lấy lịch sử để xuất.");
            });
    });

    // --- Initial Load ---
    connectSSE(); // Start the connection process

}); // End DOMContentLoaded