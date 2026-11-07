
document.addEventListener('DOMContentLoaded', function() {
    const editor = document.getElementById('configJsonEditor');
    const badge = document.getElementById('jsonStatusBadge');
    const saveBtn = document.getElementById('saveBtn');

    function validateJSON() {
        try {
            JSON.parse(editor.value);
            badge.className = 'badge bg-success';
            badge.innerHTML = '<i class="fa-solid fa-check-circle me-1"></i>Valid JSON';
            saveBtn.disabled = false;
        } catch (e) {
            badge.className = 'badge bg-danger';
            badge.innerHTML = '<i class="fa-solid fa-triangle-exclamation me-1"></i>Invalid JSON Syntax';
            saveBtn.disabled = true;
        }
    }

    if (editor) {
        editor.addEventListener('input', validateJSON);
    }
});
