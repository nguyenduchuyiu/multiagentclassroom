document.addEventListener('DOMContentLoaded', () => {
    // Lấy các phần tử DOM quan trọng
    const chatbox = document.getElementById('chatMessages');
    const messageInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendBtn');
    const typingIndicator = document.getElementById('typingIndicator');
    const participantsList = document.getElementById('participantsList'); // Vùng chứa participant
    const messageCountEl = document.getElementById('messageCount');
    const turnCountEl = document.getElementById('turnCount'); // Có thể không dùng 'turn'
    const connectionStatusIcon = document.getElementById('connectionStatusIcon');
    const statusText = document.getElementById('statusText');
    const restartBtn = document.getElementById('restartBtn');
    const exportBtn = document.getElementById('exportBtn');
    // Thêm các phần tử khác nếu cần cập nhật động (stage, progress, etc.)

    let messageCounter = 0;
    let currentTypingAgents = new Set(); // Lưu trữ ID các agent đang typing

    // --- Hàm tiện ích ---

    // Định dạng thời gian (ví dụ đơn giản)
    function formatTimestamp(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // Hàm hiển thị tin nhắn mới vào chatbox
    function displayMessage(sender, text, timestamp, senderType = 'ai', agentId = null) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message');

        let senderClass = '';
        let messageContent = '';

        if (senderType === 'user') {
            messageDiv.classList.add('user-message');
            senderClass = 'user-message'; // Class cho message-content
            messageContent = `
                <div class="message-header">
                    <strong class="sender-name">Bạn</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content">
                    <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        } else if (senderType === 'system') {
            messageDiv.classList.add('system-message'); // Thêm class riêng cho hệ thống nếu muốn
            senderClass = 'system-message';
             messageContent = `
                <div class="message-header">
                    <strong class="sender-name">${sender}</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content" style="background-color: #f0f0f0; font-style: italic;">
                    <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        }
        else { // AI message
            messageDiv.classList.add('ai-message');
            // Thêm class dựa trên agentId để CSS áp dụng màu border/avatar
            if (agentId) {
                messageDiv.classList.add(`sender-${agentId}`);
                 senderClass = `sender-${agentId}`;
            }
            messageContent = `
                 <div class="message-header">
                    <strong class="sender-name">${sender}</strong>
                    <span class="timestamp">${formatTimestamp(timestamp)}</span>
                </div>
                <div class="message-content">
                     <div class="message-text">${escapeHTML(text)}</div>
                </div>`;
        }

        messageDiv.innerHTML = messageContent;
        chatbox.appendChild(messageDiv);

        // Tự động cuộn xuống cuối
        chatbox.scrollTop = chatbox.scrollHeight;

        // Cập nhật bộ đếm tin nhắn
        messageCounter++;
        messageCountEl.textContent = messageCounter;
        // Cập nhật lượt (nếu cần logic riêng)
        // turnCountEl.textContent = ...;

        // Xử lý MathJax nếu có công thức toán
        if (typeof MathJax !== 'undefined' && MathJax.typesetPromise) {
             MathJax.typesetPromise([messageDiv]).catch(function (err) {
                 console.error('MathJax typesetting error:', err);
             });
        }
    }

     // Hàm thoát HTML để tránh XSS
     function escapeHTML(str) {
        const div = document.createElement('div');
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
     }


    // Hàm cập nhật chỉ báo typing
    function updateTypingIndicator() {
        if (currentTypingAgents.size === 0) {
            typingIndicator.innerHTML = ''; // Xóa nếu không ai đang nhập
            typingIndicator.style.display = 'none'; // Ẩn vùng chỉ báo
        } else {
            const agentNames = Array.from(currentTypingAgents).join(', ');
            typingIndicator.innerHTML = `<span>${agentNames} đang nhập...</span>`;
            typingIndicator.style.display = 'block'; // Hiện vùng chỉ báo
        }

        // Cập nhật trạng thái trong panel người tham gia
        const participantDivs = participantsList.querySelectorAll('.participant');
        participantDivs.forEach(div => {
            const agentId = div.id.replace('participant-', ''); // Lấy agentId từ id div
            const statusElement = div.querySelector(`#status-${agentId}`);
            const typingDot = div.querySelector('.typing-dot');

            if (statusElement && typingDot) {
                if (currentTypingAgents.has(agentId)) {
                    statusElement.textContent = 'Typing '; // Text trạng thái
                    typingDot.style.display = 'inline-block'; // Hiện dấu chấm
                } else {
                    // Chỉ đặt lại thành Idle nếu không phải người dùng
                    if(agentId !== 'Human'){
                        statusElement.textContent = 'Idle ';
                        typingDot.style.display = 'none'; // Ẩn dấu chấm
                    }
                }
            }
        });
    }

    // Hàm cập nhật trạng thái kết nối
    function updateConnectionStatus(status) {
        const statusElement = document.querySelector('.status');
        statusElement.classList.remove('connecting', 'connected', 'disconnected'); // Xóa class cũ

        switch (status) {
            case 'connected':
                connectionStatusIcon.style.color = 'var(--success-color)';
                statusText.textContent = 'Đã kết nối';
                statusElement.classList.add('connected');
                messageInput.disabled = false; // Cho phép nhập liệu
                sendButton.disabled = false;
                break;
            case 'disconnected':
                connectionStatusIcon.style.color = 'var(--error-color)';
                statusText.textContent = 'Mất kết nối';
                statusElement.classList.add('disconnected');
                messageInput.disabled = true; // Không cho nhập liệu
                sendButton.disabled = true;
                // Có thể thêm logic thử kết nối lại ở đây
                break;
            default: // connecting or initial state
                connectionStatusIcon.style.color = 'var(--warning-color)';
                statusText.textContent = 'Đang kết nối...';
                statusElement.classList.add('connecting');
                messageInput.disabled = true;
                sendButton.disabled = true;
        }
    }

    // --- Xử lý gửi tin nhắn ---
    function sendMessage() {
        const text = messageInput.value.trim();
        if (text && !messageInput.disabled) { // Chỉ gửi nếu có text và không bị disable
            // Vô hiệu hóa tạm thời để tránh gửi liên tục
            messageInput.disabled = true;
            sendButton.disabled = true;
            sendButton.classList.add('disabled'); // Thêm class disabled

            fetch('/send_message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ text: text }),
            })
            .then(response => {
                if (!response.ok) {
                    console.error("Gửi tin nhắn thất bại:", response.statusText);
                    // Có thể hiển thị lỗi cho người dùng
                    displayMessage('System', `Lỗi gửi tin nhắn: ${response.statusText}`, Date.now(), 'system');
                }
                 // Không cần làm gì khi thành công, SSE sẽ xử lý tin nhắn mới
            })
            .catch(error => {
                console.error('Lỗi mạng khi gửi tin nhắn:', error);
                 displayMessage('System', `Lỗi mạng: ${error.message}`, Date.now(), 'system');
            })
            .finally(() => {
                // Cho phép nhập lại sau khi gửi xong (dù thành công hay lỗi)
                // Server sẽ cập nhật trạng thái connected/disconnected qua SSE nếu cần
                if(eventSource && eventSource.readyState === EventSource.OPEN) {
                     messageInput.disabled = false;
                     sendButton.disabled = false;
                     sendButton.classList.remove('disabled');
                     messageInput.focus(); // Focus lại vào ô input
                }
            });

            messageInput.value = ''; // Xóa input ngay sau khi lấy giá trị
            messageInput.style.height = 'auto'; // Reset chiều cao textarea
        }
    }

    // --- Lắng nghe sự kiện ---
    sendButton.addEventListener('click', sendMessage);

    messageInput.addEventListener('keypress', (e) => {
        // Gửi khi nhấn Enter (không nhấn Shift)
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault(); // Ngăn xuống dòng mặc định
            sendMessage();
        }
    });

     // Tự động điều chỉnh chiều cao textarea khi nhập
     messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto'; // Reset chiều cao
        messageInput.style.height = (messageInput.scrollHeight) + 'px'; // Đặt chiều cao mới
     });


    // --- Thiết lập Server-Sent Events (SSE) ---
    let eventSource = null;

    function connectSSE() {
        if (eventSource && (eventSource.readyState === EventSource.OPEN || eventSource.readyState === EventSource.CONNECTING)) {
            console.log("SSE connection already open or connecting.");
            return;
        }

        console.log("Connecting to SSE stream...");
        updateConnectionStatus('connecting'); // Cập nhật trạng thái UI

        eventSource = new EventSource('/stream');

        eventSource.onopen = function() {
            console.log("SSE connection established.");
            updateConnectionStatus('connected'); // Cập nhật trạng thái UI
            // Lấy lịch sử chat khi kết nối thành công
             fetch('/history')
                .then(response => response.json())
                .then(history => {
                    chatbox.innerHTML = ''; // Xóa chat cũ (nếu có)
                    messageCounter = 0; // Reset counter
                    history.forEach(msg => {
                        const senderType = msg.sender === 'Human' ? 'user' : (msg.sender === 'System' ? 'system' : 'ai');
                        const agentId = senderType === 'ai' ? msg.sender : null;
                        displayMessage(msg.sender, msg.text, msg.timestamp, senderType, agentId);
                    });
                    messageInput.focus(); // Focus vào ô nhập liệu
                })
                .catch(error => console.error("Error fetching history:", error));
        };

        eventSource.onerror = function(err) {
            console.error("SSE error:", err);
            updateConnectionStatus('disconnected');
            eventSource.close(); // Đóng kết nối cũ
            // Thử kết nối lại sau một khoảng thời gian
            setTimeout(connectSSE, 5000); // Thử lại sau 5 giây
        };

        // Lắng nghe sự kiện 'new_message'
        eventSource.addEventListener('new_message', function(event) {
            try {
                const message = JSON.parse(event.data);
                console.log("SSE new_message:", message);
                const senderType = message.sender === 'Human' ? 'user' : (message.sender === 'System' ? 'system' : 'ai');
                 const agentId = senderType === 'ai' ? message.sender : null;
                displayMessage(message.sender, message.text, message.timestamp, senderType, agentId);
                 // Khi có tin nhắn mới, xóa hết trạng thái typing
                 currentTypingAgents.clear();
                 updateTypingIndicator();
            } catch (e) {
                console.error("Error parsing new_message data:", e, event.data);
            }
        });

        // Lắng nghe sự kiện 'agent_status'
        eventSource.addEventListener('agent_status', function(event) {
            try {
                const statusUpdate = JSON.parse(event.data);
                console.log("SSE agent_status:", statusUpdate);
                if (statusUpdate.status === 'typing') {
                    currentTypingAgents.add(statusUpdate.agent_id);
                } else {
                    currentTypingAgents.delete(statusUpdate.agent_id);
                }
                updateTypingIndicator();
            } catch (e) {
                console.error("Error parsing agent_status data:", e, event.data);
            }
        });

         // (Tùy chọn) Lắng nghe các sự kiện khác từ server nếu cần
         // eventSource.addEventListener('progress_update', function(event) { ... });
         // eventSource.addEventListener('stats_update', function(event) { ... });

    }

    // --- Xử lý các nút điều khiển khác ---
    restartBtn.addEventListener('click', () => {
        if (confirm("Bạn có chắc muốn bắt đầu lại cuộc trò chuyện? Toàn bộ lịch sử sẽ bị xóa.")) {
            console.log("Restarting conversation...");
            // TODO: Gửi yêu cầu tới backend để reset trạng thái (nếu cần)
            // fetch('/restart', { method: 'POST' }).then(...)

            // Reset frontend
            chatbox.innerHTML = '';
            messageCounter = 0;
            messageCountEl.textContent = '0';
            turnCountEl.textContent = '0'; // Reset lượt
            currentTypingAgents.clear();
            updateTypingIndicator();
            // Reset progress, stage...
            // Hiển thị lại tin nhắn chào mừng (nếu có)
            // displayMessage('System', 'Cuộc trò chuyện đã được khởi động lại.', Date.now(), 'system');

             // Đóng và mở lại SSE để đảm bảo trạng thái sạch
             if (eventSource) {
                eventSource.close();
             }
             setTimeout(connectSSE, 500); // Kết nối lại sau 0.5s
        }
    });

    exportBtn.addEventListener('click', () => {
        console.log("Exporting conversation...");
        // Lấy nội dung chat
        let chatContent = "";
        const messages = chatbox.querySelectorAll('.message');
        messages.forEach(msg => {
            const sender = msg.querySelector('.sender-name')?.textContent || 'Unknown';
            const text = msg.querySelector('.message-text')?.textContent || '';
            const time = msg.querySelector('.timestamp')?.textContent || '';
            chatContent += `[${time}] ${sender} ${text}\n`;
        });

        if (!chatContent) {
            alert("Không có nội dung để xuất.");
            return;
        }

        // Tạo file và tải xuống
        const blob = new Blob([chatContent], { type: 'text/plain;charset=utf-8' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `chatcollab_export_${new Date().toISOString().slice(0,10)}.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href); // Giải phóng bộ nhớ
    });


    // --- Khởi tạo kết nối SSE ban đầu ---
    connectSSE();

}); // Kết thúc DOMContentLoaded