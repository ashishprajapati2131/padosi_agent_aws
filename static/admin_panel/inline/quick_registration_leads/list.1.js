
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.copy-phone-btn').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            var phone = this.getAttribute('data-phone');
            if (!phone) return;
            navigator.clipboard.writeText(phone).then(function() {
                var icon = btn.querySelector('i');
                if (icon) {
                    icon.className = 'fa-solid fa-check text-success';
                    setTimeout(function() {
                        icon.className = 'fa-regular fa-copy';
                    }, 1500);
                }
            });
        });
    });
});
