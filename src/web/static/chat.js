(function() {
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('message-input');
    const sendBtn = document.getElementById('send-btn');
    const newSessionBtn = document.getElementById('new-session-btn');

    function getSessionId() {
        let sid = localStorage.getItem('session_id');
        if (!sid) {
            sid = crypto.randomUUID?.() ?? 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0;return(c=='x'?r:r&0x3|0x8).toString(16)});
            localStorage.setItem('session_id', sid);
        }
        return sid;
    }

    function addMessage(text, role) {
        const el = document.createElement('div');
        el.className = 'msg ' + role;
        el.textContent = text;
        messagesEl.appendChild(el);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text) return;
        inputEl.value = '';
        sendBtn.disabled = true;

        addMessage(text, 'user');

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text, session_id: getSessionId() }),
            });
            const data = await res.json();
            addMessage(data.reply, 'bot');
        } catch (e) {
            addMessage('⚠️ Ошибка соединения с сервером', 'bot');
        } finally {
            sendBtn.disabled = false;
            inputEl.focus();
        }
    }

    async function newSession() {
        await fetch('/api/session/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: getSessionId() }),
        });
        messagesEl.innerHTML = '';
        addMessage('🔄 Новая сессия начата. История диалога очищена.', 'bot');
        inputEl.focus();
    }

    sendBtn.addEventListener('click', sendMessage);
    inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') sendMessage();
    });
    newSessionBtn.addEventListener('click', newSession);
})();
