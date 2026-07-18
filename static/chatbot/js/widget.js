document.addEventListener('DOMContentLoaded', () => {
    const triggerBtn = document.getElementById('chatbot-trigger');
    const closeBtn = document.getElementById('chatbot-close');
    const panel = document.getElementById('chatbot-panel');
    const input = document.getElementById('chatbot-input');
    const sendBtn = document.getElementById('chatbot-send');
    const messagesContainer = document.getElementById('chatbot-messages');
    const suggestionsContainer = document.getElementById('chatbot-suggestions');
    let chips = document.querySelectorAll('.chatbot-chip');

    if (!triggerBtn || !panel) return; // fail gracefully if not on page

    let sessionId = localStorage.getItem('chatbot_session_id') || "";

    const loadChips = () => {
        fetch('/chatbot/chips/')
            .then(res => res.json())
            .then(data => {
                if (data.success && data.data && suggestionsContainer) {
                    suggestionsContainer.innerHTML = '';
                    data.data.forEach(chipText => {
                        const chip = document.createElement('button');
                        chip.className = 'chatbot-chip';
                        chip.textContent = chipText;
                        chip.addEventListener('click', (e) => {
                            sendMessage(e.target.textContent);
                        });
                        suggestionsContainer.appendChild(chip);
                    });
                }
            }).catch(err => console.error("Error loading chips", err));
    };

    const loadHistory = async () => {
        if (!sessionId) {
            loadChips();
            return;
        }
        try {
            const res = await fetch(`/chatbot/history/${sessionId}/`);
            const data = await res.json();
            if (data.success && data.data && data.data.length > 0) {
                // Clear welcome message and chips
                messagesContainer.innerHTML = ''; 
                
                data.data.forEach(msg => {
                    const msgDiv = document.createElement('div');
                    msgDiv.className = `chatbot-message ${msg.role === 'user' ? 'user-message' : 'bot-message'}`;
                    if (msg.role === 'assistant') {
                        msgDiv.innerHTML = msg.content.replace(/\n/g, '<br>');
                    } else {
                        msgDiv.textContent = msg.content;
                    }
                    messagesContainer.appendChild(msgDiv);
                });
                
                // Scroll to bottom
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            } else {
                loadChips();
            }
        } catch (err) {
            console.error("Error loading history", err);
            loadChips();
        }
    };

    loadHistory();

    // Toggle panel
    triggerBtn.addEventListener('click', () => {
        panel.classList.remove('hidden');
        triggerBtn.style.display = 'none';
        input.focus();
    });

    closeBtn.addEventListener('click', () => {
        panel.classList.add('hidden');
        setTimeout(() => {
            triggerBtn.style.display = 'flex';
        }, 300); // Wait for transition
    });

    // Auto-scroll
    const scrollToBottom = () => {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    };

    // Send message functionality
    const sendMessage = async (text) => {
        if (!text || text.trim() === '') return;

        // Hide suggestions if they exist
        if (suggestionsContainer) {
            suggestionsContainer.style.display = 'none';
        }
        
        // Remove old quick options
        const oldOptions = messagesContainer.querySelectorAll('.chatbot-quick-options');
        oldOptions.forEach(opt => opt.remove());

        // Add user message
        const userMsgDiv = document.createElement('div');
        userMsgDiv.className = 'chatbot-message user-message';
        userMsgDiv.textContent = text;
        messagesContainer.appendChild(userMsgDiv);
        scrollToBottom();

        // Add typing indicator
        const typingDiv = document.createElement('div');
        typingDiv.className = 'chatbot-message bot-message';
        typingDiv.textContent = "Typing...";
        typingDiv.style.fontStyle = "italic";
        typingDiv.style.opacity = "0.7";
        messagesContainer.appendChild(typingDiv);
        scrollToBottom();

        try {
            const response = await fetch('/chatbot/message/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: text, session_id: sessionId })
            });
            
            const data = await response.json();
            
            if (messagesContainer.contains(typingDiv)) {
                messagesContainer.removeChild(typingDiv);
            }

            if (data.success) {
                if (data.session_id) {
                    sessionId = data.session_id;
                    localStorage.setItem('chatbot_session_id', sessionId);
                }
                const botMsgDiv = document.createElement('div');
                botMsgDiv.className = 'chatbot-message bot-message';
                botMsgDiv.innerHTML = data.data.reply.replace(/\n/g, '<br>');
                messagesContainer.appendChild(botMsgDiv);
                
                // Render quick options if present
                if (data.data.quick_options && data.data.quick_options.length > 0) {
                    const quickOptionsDiv = document.createElement('div');
                    quickOptionsDiv.className = 'chatbot-quick-options chatbot-suggestions-row';
                    quickOptionsDiv.style.marginTop = '8px';
                    data.data.quick_options.forEach(optText => {
                        const chip = document.createElement('button');
                        chip.className = 'chatbot-chip';
                        chip.textContent = optText;
                        chip.addEventListener('click', (e) => {
                            sendMessage(e.target.textContent);
                        });
                        quickOptionsDiv.appendChild(chip);
                    });
                    messagesContainer.appendChild(quickOptionsDiv);
                }
            } else {
                const errorMsg = document.createElement('div');
                errorMsg.className = 'chatbot-message bot-message';
                errorMsg.textContent = data.error || "Something went wrong.";
                messagesContainer.appendChild(errorMsg);
            }
        } catch (err) {
            if (messagesContainer.contains(typingDiv)) {
                messagesContainer.removeChild(typingDiv);
            }
            const errorMsg = document.createElement('div');
            errorMsg.className = 'chatbot-message bot-message';
            errorMsg.textContent = "Error connecting to assistant.";
            messagesContainer.appendChild(errorMsg);
        }
        scrollToBottom();
    };

    // Input active state
    const updateSendBtnState = () => {
        if (input.value.trim().length > 0) {
            sendBtn.classList.add('send-btn--active');
        } else {
            sendBtn.classList.remove('send-btn--active');
        }
    };

    input.addEventListener('input', updateSendBtnState);

    // Event listeners for sending
    sendBtn.addEventListener('click', () => {
        const text = input.value;
        if (text.trim()) {
            sendMessage(text);
            input.value = '';
            updateSendBtnState();
        }
    });

    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const text = input.value;
            if (text.trim()) {
                sendMessage(text);
                input.value = '';
                updateSendBtnState();
            }
        }
    });

    // Chip clicks
    chips.forEach(chip => {
        chip.addEventListener('click', (e) => {
            const text = e.target.textContent;
            sendMessage(text);
        });
    });
});
