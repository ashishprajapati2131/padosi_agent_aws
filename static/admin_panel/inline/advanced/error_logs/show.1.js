
    function copyTraceback() {
        const codeElement = document.getElementById('tracebackCode');
        if (!codeElement) return;

        navigator.clipboard.writeText(codeElement.textContent)
            .then(() => {
                if (typeof Swal !== 'undefined') {
                    Swal.fire({
                        toast: true,
                        position: 'top-end',
                        icon: 'success',
                        title: 'Copied to clipboard!',
                        showConfirmButton: false,
                        timer: 1500
                    });
                } else {
                    alert('Copied to clipboard!');
                }
            })
            .catch(err => console.error('Could not copy text: ', err));
    }
