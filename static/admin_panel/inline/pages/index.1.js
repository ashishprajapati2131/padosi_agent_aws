
document.querySelectorAll('.delete-page-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        var pageId    = this.dataset.pageId;
        var pageTitle = this.dataset.pageTitle;

        if (!confirm('Delete page "' + pageTitle + '"?\n\nThis is permanent and cannot be undone.')) return;

        var form = document.getElementById('delete-form-' + pageId);
        if (form) form.submit();
    });
});
