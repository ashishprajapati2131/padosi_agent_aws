
// ─── Tab Switcher ───────────────────────────────────────────────────────────
function switchTab(tab) {
    const single    = document.getElementById('panel-single');
    const broadcast = document.getElementById('panel-broadcast');
    const tabSingle = document.getElementById('tab-single');
    const tabBc     = document.getElementById('tab-broadcast');

    if (tab === 'single') {
        single.style.display = 'block';
        broadcast.style.display = 'none';
        tabSingle.style.color = 'var(--primary)';
        tabSingle.style.borderBottomColor = 'var(--primary)';
        tabBc.style.color = 'var(--text-muted)';
        tabBc.style.borderBottomColor = 'transparent';
    } else {
        single.style.display = 'none';
        broadcast.style.display = 'block';
        tabBc.style.color = 'var(--primary)';
        tabBc.style.borderBottomColor = 'var(--primary)';
        tabSingle.style.color = 'var(--text-muted)';
        tabSingle.style.borderBottomColor = 'transparent';
    }
}

// ─── Live Preview: Single ───────────────────────────────────────────────────
function updateSinglePreview() {
    const t = document.getElementById('single_title').value.trim();
    const b = document.getElementById('single_body').value.trim();
    const preview = document.getElementById('singlePreview');
    if (t || b) {
        preview.style.display = 'block';
        document.getElementById('previewTitle').textContent = t || 'Your Title Here';
        document.getElementById('previewBody').textContent  = b || 'Your message...';
    } else {
        preview.style.display = 'none';
    }
}

document.getElementById('single_title').addEventListener('input', function() {
    document.getElementById('titleCount').textContent = this.value.length + ' / 100';
    updateSinglePreview();
});
document.getElementById('single_body').addEventListener('input', function() {
    document.getElementById('bodyCount').textContent = this.value.length + ' / 255';
    updateSinglePreview();
});

// ─── Live Preview: Broadcast ────────────────────────────────────────────────
function updateBcPreview() {
    const t = document.getElementById('bc_title').value.trim();
    const b = document.getElementById('bc_body').value.trim();
    const preview = document.getElementById('broadcastPreview');
    if (t || b) {
        preview.style.display = 'block';
        document.getElementById('bcPreviewTitle').textContent = t || 'Your Title Here';
        document.getElementById('bcPreviewBody').textContent  = b || 'Your message...';
    } else {
        preview.style.display = 'none';
    }
}

document.getElementById('bc_title').addEventListener('input', function() {
    document.getElementById('bcTitleCount').textContent = this.value.length + ' / 100';
    updateBcPreview();
});
document.getElementById('bc_body').addEventListener('input', function() {
    document.getElementById('bcBodyCount').textContent = this.value.length + ' / 255';
    updateBcPreview();
});

// ─── Target Pill Selection ──────────────────────────────────────────────────
document.querySelectorAll('.target-pill').forEach(pill => {
    pill.addEventListener('click', function() {
        document.querySelectorAll('.target-pill').forEach(p => p.classList.remove('selected'));
        this.classList.add('selected');
    });
});

// ─── Quick Send from Table ──────────────────────────────────────────────────
function quickSend(agentId, agentName) {
    document.getElementById('qs_agentId').value = agentId;
    document.getElementById('qs_agentName').textContent = agentName;
    document.getElementById('qs_title').value = '';
    document.getElementById('qs_body').value = '';
    document.getElementById('qs_previewTitle').textContent = 'Title preview';
    document.getElementById('qs_previewBody').textContent = 'Message preview...';
    $('#quickSendModal').modal('show');
}

// ─── Form Submit Guards ─────────────────────────────────────────────────────
document.getElementById('singleNotifForm').addEventListener('submit', function() {
    const btn = document.getElementById('singleSendBtn');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Sending...';
    btn.disabled = true;
});

document.getElementById('broadcastPushForm').addEventListener('submit', function(e) {
    if (!confirm('Send this push notification to ALL matching agents? This cannot be undone.')) {
        e.preventDefault();
        return;
    }
    const btn = document.getElementById('broadcastSendBtn');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Broadcasting...';
    btn.disabled = true;
});
