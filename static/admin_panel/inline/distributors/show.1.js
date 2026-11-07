
// Populate the sub-distributor reset modal with the clicked row's id + name.
document.querySelectorAll('.reset-subdist-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        document.getElementById('reset-sub-id').value = this.getAttribute('data-id');
        document.getElementById('reset-sub-name').textContent = this.getAttribute('data-name') || '';
    });
});

// "Generate a strong password" — fills both password fields in the same form.
function makePassword(len) {
    const chars = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789@#$%';
    let out = '';
    const arr = new Uint32Array(len);
    (window.crypto || window.msCrypto).getRandomValues(arr);
    for (let i = 0; i < len; i++) out += chars[arr[i] % chars.length];
    return out;
}
document.querySelectorAll('.gen-pwd-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
        const form = this.closest('form');
        const pwd = makePassword(12);
        form.querySelector('input[name="password"]').value = pwd;
        form.querySelector('input[name="confirm_password"]').value = pwd;
    });
});
