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
    const statusTextEl = document.getElementById('statusText');
    const statusIndicatorEl = document.querySelector('.status');
    const statusIconEl = document.getElementById('connectionStatusIcon');
    const restartBtn = document.getElementById('restartBtn');
    const exportBtn = document.getElementById('exportBtn');
    const currentStageEl = document.getElementById('currentStage');
    const stageDescriptionEl = document.getElementById('stageDescription');
    const progressFillEl = document.getElementById('progressFill');
    const progressStageMarkersEl = document.getElementById('progressStageMarkers');
    const subTasksListEl = document.getElementById('subTasksList');
    const progressLabelEl = document.getElementById('progressLabel');
    const progressBarEl = document.querySelector('.progress-bar');
    const progressPercentEl = document.getElementById('progressPercent');

    // --- State Variables ---
    let messageCounter = 0;
    let currentTypingAgents = new Set();
    let agentStatuses = {};
    let socket = null;

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
            if (agentName) {
                agentStatuses[agentName] = 'idle';
            }
        });
        console.log('Final agentStatuses object after initialization:', JSON.stringify(agentStatuses));
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

        html = `
            <div class="message-header">
                <strong class="sender-name">${escapeHTML(senderName)}</strong>
                <span class="timestamp">${timeStr}</span>
            </div>
            <div class="message-content">
                <div class="message-text"></div>
            </div>`;

        msg.innerHTML = html;

        const messageTextDiv = msg.querySelector('.message-text');
        if (messageTextDiv) {
            messageTextDiv.innerHTML = text;
        }

        chatbox.appendChild(msg);
        renderMathInElement(msg.querySelector('.message-text'));
        chatbox.scrollTop = chatbox.scrollHeight;

        messageCounter++;
        if (messageCountEl) messageCountEl.textContent = messageCounter;
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
        if (!statusIndicatorEl || !statusTextEl || !messageInput || !sendButton) {
            console.warn("Status display elements not found, cannot update connection status.");
            return;
        }

        statusIndicatorEl.classList.remove('connecting', 'connected', 'disconnected');
        messageInput.disabled = true; // Disable input by default
        sendButton.disabled = true;

        switch(status) {
            case 'connected':
                statusTextEl.textContent = 'Đã kết nối';
                statusIndicatorEl.classList.add('connected');
                if (statusIconEl) {
                    statusIconEl.style.animationName = 'none'; // Stop pulsing
                    statusIconEl.style.opacity = '1';          // Ensure dot is solid
                }
                messageInput.disabled = false; // Enable input on connection
                sendButton.disabled = false;
                break;
            case 'connecting':
                statusTextEl.textContent = 'Đang kết nối...';
                statusIndicatorEl.classList.add('connecting');
                if (statusIconEl) {
                    statusIconEl.style.animationName = 'pulse'; // Ensure pulsing
                }
                // Inputs remain disabled (already set by default)
                break;
            case 'disconnected':
                statusTextEl.textContent = 'Đã mất kết nối';
                statusIndicatorEl.classList.add('disconnected');
                if (statusIconEl) {
                    statusIconEl.style.animationName = 'none'; // Stop pulsing
                    statusIconEl.style.opacity = '1';          // Ensure dot is solid
                }
                // Inputs remain disabled (already set by default)
                break;
            default:
                statusTextEl.textContent = 'Trạng thái không xác định';
                if (statusIconEl) {
                     statusIconEl.style.animationName = 'pulse'; // Default to pulsing
                }
                // Inputs remain disabled
        }
    }

    function sendMessage() {
        if (!messageInput || !sendButton) return; // Check elements exist

        const text = messageInput.value.trim();
        if (!currentUsername) initializeUserDisplay(); // Make sure username is set
        if (!text || messageInput.disabled) return;

        messageInput.disabled = true;
        sendButton.disabled = true;

        // Use Socket.IO instead of fetch for sending messages
        socket.emit('user_message', {
            session_id: currentSessionId,
            text: text,
            sender_name: currentUsername
        });

        // Clear the input after sending
        messageInput.value = '';
        messageInput.style.height = 'auto';
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

    // --- Socket.IO Setup ---
    function connectSocketIO() {
        updateConnectionStatus('connecting');
        
        // Initialize Socket.IO connection
        socket = io();
        
        // Connection events
        socket.on('connect', () => {
            console.log('Connected to Socket.IO server');
            updateConnectionStatus('connected');
            
            // Join the session room
            socket.emit('join', { session_id: currentSessionId });
            
            initializeUserDisplay();
            initializeAgentStatuses();
            renderMathInElement(problemDisplayEl);
            
            // Fetch initial chat history
            fetch(`/history/${currentSessionId}`)
                .then(r => {
                    if (!r.ok) throw new Error(`HTTP error! status: ${r.status}`);
                    return r.json()
                })
                .then(history => {
                    if (chatbox) chatbox.innerHTML = '';
                    messageCounter = 0;
                    history.forEach(displayMessage);
                    if (messageInput) messageInput.focus();
                })
                .catch(err => {
                    console.error("History fetch error:", err);
                    displayMessage({ 
                        source: 'System', 
                        content: { text: 'Không thể tải lịch sử.', sender_name: 'System' }, 
                        timestamp: Date.now() 
                    });
                });
        });
        
        socket.on('disconnect', () => {
            console.log('Disconnected from Socket.IO server');
            updateConnectionStatus('disconnected');
        });
        
        socket.on('error', (data) => {
            console.error('Socket.IO error:', data.message);
            displayMessage({ 
                source: 'System', 
                content: { text: `Lỗi: ${data.message}`, sender_name: 'System' }, 
                timestamp: Date.now() 
            });
        });
        
        socket.on('joined', (data) => {
            console.log('Successfully joined session:', data.session_id);
        });
        
        socket.on('message_received', (data) => {
            console.log('Message received confirmation:', data);
            // Re-enable input fields
            if (messageInput) messageInput.disabled = false;
            if (sendButton) sendButton.disabled = false;
            if (messageInput) messageInput.focus();
        });
        
        // Handle incoming messages
        socket.on('new_message', (data) => {
            console.log("New message received:", data); // Debug: Log the received data
            displayMessage(data);
            
            // If it's an agent message, clear typing status
            const senderName = data.content?.sender_name;
            if (senderName && agentStatuses.hasOwnProperty(senderName)) {
                currentTypingAgents.delete(senderName);
                updateParticipantDisplay();
            }
        });
        
        // Handle agent status updates
        socket.on('agent_status', (data) => {
            try {
                const update = data.content;
                const { agent_name: nameFromEvent, status } = update;
                
                if (!nameFromEvent || !status) {
                    console.warn("Received agent_status with missing name or status:", data);
                    return;
                }
                
                let actualAgentNameKey = null;
                // Case-insensitive search for agent name
                for (const key in agentStatuses) {
                    if (agentStatuses.hasOwnProperty(key) && key.toLowerCase() === nameFromEvent.toLowerCase()) {
                        actualAgentNameKey = key;
                        break;
                    }
                }
                
                if (actualAgentNameKey) {
                    agentStatuses[actualAgentNameKey] = status;
                    if (status === 'typing') {
                        currentTypingAgents.add(actualAgentNameKey);
                    } else {
                        currentTypingAgents.delete(actualAgentNameKey);
                    }
                    updateParticipantDisplay();
                } else {
                    console.warn(
                        "Received agent_status for unknown agent:",
                        {
                            eventName: nameFromEvent,
                            eventStatus: status,
                            knownAgentKeys: Object.keys(agentStatuses)
                        }
                    );
                }
            } catch (err) {
                console.error('Error handling agent_status:', err);
            }
        });
        
        // Handle stage updates
        socket.on('stage_update', (data) => {
            try {
                const phaseInfo = data.content;
                
                console.log("[STAGE_UPDATE] Received phaseInfo:", phaseInfo);
                
                if (phaseInfo && typeof phaseInfo.id !== 'undefined' && typeof phaseInfo.name !== 'undefined') {
                    if (currentStageEl) currentStageEl.textContent = phaseInfo.name;
                    if (stageDescriptionEl) stageDescriptionEl.textContent = phaseInfo.description || 'Không có mô tả cho giai đoạn này.';
                    
                    // Update progress bar fill
                    if (progressFillEl && typeof phaseInfo.progress_bar_percent === 'number') {
                        const progressPercent = phaseInfo.progress_bar_percent;
                        console.log(`[STAGE_UPDATE] Progress bar: Using weighted progress_bar_percent = ${progressPercent.toFixed(2)}%`);
                        progressFillEl.style.width = `${Math.min(100, Math.max(0, progressPercent))}%`;
                        
                        // Display progress percentage
                        if (progressPercentEl) {
                            progressPercentEl.textContent = `(${Math.round(progressPercent)}%)`;
                        }
                        
                        // Update progress label
                        if (progressLabelEl && Array.isArray(phaseInfo.main_stage_markers)) {
                            const totalStages = phaseInfo.main_stage_markers.length;
                            const currentStageIndex = phaseInfo.main_stage_markers.findIndex(m => m.id === phaseInfo.id);
                            const currentStageNum = currentStageIndex !== -1 ? currentStageIndex + 1 : '?';
                            
                            progressLabelEl.textContent = `Giai đoạn ${currentStageNum}/${totalStages}: ${phaseInfo.name}`;
                        }
                        
                        // Create tooltip for progress bar
                        if (progressBarEl && Array.isArray(phaseInfo.main_stage_markers)) {
                            let tooltipText = phaseInfo.main_stage_markers.map((marker, idx) => {
                                const prefix = marker.id === phaseInfo.id ? '➤ ' : '';
                                return `${prefix}${idx+1}. ${marker.name || 'Giai đoạn ' + marker.id}`;
                            }).join('\n');
                            progressBarEl.setAttribute('data-tooltip', tooltipText);
                        }
                    }
                    
                    // Handle progress stage markers
                    if (progressStageMarkersEl && Array.isArray(phaseInfo.main_stage_markers)) {
                        progressStageMarkersEl.innerHTML = '';
                        const n = phaseInfo.main_stage_markers.length;
                        phaseInfo.main_stage_markers.forEach((marker, idx) => {
                            const markerEl = document.createElement('span');
                            markerEl.title = marker.name || marker.id; // Tooltip
                            let leftPercent = 0;
                            if (n === 1) {
                                leftPercent = 0;
                            } else {
                                leftPercent = (idx) * 100 / (n - 1);
                            }
                            markerEl.style.left = `${leftPercent}%`;
                            if (marker.id === phaseInfo.id) {
                                markerEl.classList.add('active-stage-marker');
                            }
                            progressStageMarkersEl.appendChild(markerEl);
                        });
                    }
                    
                    // Update subtasks list
                    if (subTasksListEl) {
                        subTasksListEl.innerHTML = '';
                        if (phaseInfo.tasks && Array.isArray(phaseInfo.tasks) && phaseInfo.tasks.length > 0) {
                            phaseInfo.tasks.forEach(task => {
                                const li = document.createElement('li');
                                li.classList.add(task.completed ? 'completed' : 'pending');
                                const icon = document.createElement('span');
                                icon.classList.add('task-status-icon');
                                icon.innerHTML = task.completed ? '&#10004;' : '&#9711;';
                                const desc = document.createElement('span');
                                desc.classList.add('task-description');
                                desc.textContent = task.description;
                                li.appendChild(icon);
                                li.appendChild(desc);
                                subTasksListEl.appendChild(li);
                            });
                        } else {
                            const li = document.createElement('li');
                            li.classList.add('no-tasks');
                            li.textContent = 'Giai đoạn này không có nhiệm vụ cụ thể.';
                            subTasksListEl.appendChild(li);
                        }
                    }
                } else {
                    console.warn("Received invalid stage_update data:", data);
                }
            } catch (err) {
                console.error('Error parsing stage_update event:', err);
            }
        });
    }

    // Start Socket.IO connection when page loads
    connectSocketIO();

}); // End DOMContentLoaded