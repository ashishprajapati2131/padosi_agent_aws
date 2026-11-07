
    function togglePassword(inputId, iconId) {
        const passInput = document.getElementById(inputId);
        const icon = document.getElementById(iconId);
        if (passInput.type === 'password') {
            passInput.type = 'text';
            icon.classList.remove('fa-eye');
            icon.classList.add('fa-eye-slash');
        } else {
            passInput.type = 'password';
            icon.classList.remove('fa-eye-slash');
            icon.classList.add('fa-eye');
        }
    }
