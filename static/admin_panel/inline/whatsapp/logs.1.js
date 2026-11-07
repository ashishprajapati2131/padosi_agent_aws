
    function viewFullMessage(content, phone, dir, timestamp) {
        document.getElementById('msgModalTitle').innerText = (dir === 'in' ? '📥 Incoming from +' : '📤 Outgoing to +') + phone;
        document.getElementById('msgModalBody').innerText = content;
        document.getElementById('msgModalMeta').innerText = 'Timestamp: ' + timestamp;
        new bootstrap.Modal(document.getElementById('fullMsgModal')).show();
    }
