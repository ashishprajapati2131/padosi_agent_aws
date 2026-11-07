
(function () {
    var form = document.getElementById('lgFilters');
    form.querySelectorAll('input[type=radio], select').forEach(function (el) {
        el.addEventListener('change', function () { form.submit(); });
    });
    document.addEventListener('click', function (ev) {
        var btn = ev.target.closest('[data-lg-action]');
        if (!btn) return;
        var body = btn.closest('.lg-body');
        if (btn.dataset.lgAction === 'frames') {
            var frames = body.querySelector('.lg-frames');
            var on = frames.classList.toggle('show-lib');
            btn.textContent = on ? 'Hide framework frames' : btn.dataset.label;
        } else if (btn.dataset.lgAction === 'copy') {
            var text = body.querySelector('.lg-copy-src').textContent;
            navigator.clipboard.writeText(text).then(function () {
                btn.innerHTML = '<i class="fa-solid fa-check me-1"></i>Copied';
                setTimeout(function () { btn.innerHTML = '<i class="fa-regular fa-copy me-1"></i>Copy for debugging'; }, 1500);
            });
        }
    });
})();
