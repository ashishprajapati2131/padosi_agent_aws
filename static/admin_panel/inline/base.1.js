
    // Shared by admin pages (was copy-pasted per template).
    function getCookie(name) {
        const match = document.cookie.split(';').map(c => c.trim()).find(c => c.startsWith(name + '='));
        return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
    }
    // One toast for every admin page (3 pages had their own). kind: true/'success',
    // false/'danger'/'error', or 'warning'/'info'. titleText keeps server messages as text.
    function showToast(message, kind) {
        const icon = (kind === undefined || kind === true || kind === 'success') ? 'success'
            : (kind === false || kind === 'danger' || kind === 'error') ? 'error'
            : (kind === 'warning' || kind === 'info') ? kind : 'info';
        Swal.fire({toast: true, position: 'top-end', icon: icon, titleText: String(message),
                   showConfirmButton: false, timer: icon === 'success' ? 2500 : 4500, timerProgressBar: true});
    }
    