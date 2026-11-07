
        // Global fix: Prevent number inputs from changing value on mouse scroll
        document.addEventListener('wheel', function (e) {
            if (document.activeElement.type === 'number') {
                document.activeElement.blur();
            }
        });
    