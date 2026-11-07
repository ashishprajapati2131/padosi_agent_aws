
document.getElementById('broadcast_message').addEventListener('input', function() {
    document.getElementById('charCount').textContent = this.value.length + ' chars';
});

function previewMessage() {
    const subject = document.getElementById('broadcast_subject').value || '(No subject)';
    const message = document.getElementById('broadcast_message').value || '(No message)';
    document.getElementById('previewSubject').textContent = subject;
    document.getElementById('previewBody').textContent = 'Dear [Agent Name],\n\n' + message + '\n\nBest regards,\nPadosiAgent Team';
    const modal = new bootstrap.Modal(document.getElementById('previewModal'));
    modal.show();
}

document.getElementById('broadcastForm').addEventListener('submit', function(e) {
    const subject = document.getElementById('broadcast_subject').value.trim();
    const message = document.getElementById('broadcast_message').value.trim();
    
    // Ensure at least one delivery channel is selected
    const emailChecked = document.getElementById('ch_email').checked;
    const notifChecked = document.getElementById('ch_notif').checked;
    
    if (!subject || !message) { 
        e.preventDefault(); 
        return; 
    }
    
    if (!emailChecked && !notifChecked) {
        e.preventDefault();
        Swal.fire({
            title: 'No Channel Selected',
            text: 'Please select at least one delivery channel (Email or Push Notification).',
            icon: 'warning',
            confirmButtonText: 'OK'
        });
        return;
    }
    
    if (!confirm('Are you sure you want to send this broadcast to the selected agents?')) {
        e.preventDefault();
    } else {
        document.getElementById('sendBtn').innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Sending...';
        document.getElementById('sendBtn').disabled = true;
    }
});
