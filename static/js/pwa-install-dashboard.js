/**
 * Agent dashboard — Install PWA button (beforeinstallprompt + iOS Add to Home Screen).
 */
(function () {
    'use strict';

    var BTN_ID = 'pwaInstallAppBtn';
    var IOS_MODAL_ID = 'pwaInstallIosModal';
    var deferredPrompt = null;

    function isStandalone() {
        return (
            window.matchMedia('(display-mode: standalone)').matches ||
            window.matchMedia('(display-mode: fullscreen)').matches ||
            window.navigator.standalone === true
        );
    }

    function isIosSafariInstallable() {
        var ua = window.navigator.userAgent || '';
        var isIOS =
            /iPad|iPhone|iPod/.test(ua) ||
            (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1);
        return isIOS && !isStandalone();
    }

    function getBtn() {
        return document.getElementById(BTN_ID);
    }

    function showInstallButton() {
        var btn = getBtn();
        if (btn) {
            btn.classList.remove('d-none');
            btn.setAttribute('aria-hidden', 'false');
        }
    }

    function hideInstallButton() {
        var btn = getBtn();
        if (btn) {
            btn.classList.add('d-none');
            btn.setAttribute('aria-hidden', 'true');
        }
    }

    function openIosModal() {
        var el = document.getElementById(IOS_MODAL_ID);
        if (!el) {
            return;
        }
        if (window.jQuery && typeof window.jQuery(el).modal === 'function') {
            window.jQuery(el).modal('show');
            return;
        }
        el.classList.add('show');
        el.style.display = 'block';
        el.removeAttribute('aria-hidden');
        document.body.classList.add('modal-open');
    }

    function onInstallClick() {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.then(function (result) {
                deferredPrompt = null;
                if (result.outcome === 'accepted') {
                    hideInstallButton();
                }
            });
            return;
        }

        if (isIosSafariInstallable()) {
            openIosModal();
            return;
        }

        if (typeof window.Swal !== 'undefined') {
            window.Swal.fire({
                icon: 'info',
                title: 'Install the app',
                html:
                    '<p style="font-size:15px;line-height:1.5;margin:0;">Open your browser menu and choose ' +
                    '<strong>Install app</strong> or <strong>Add to Home screen</strong>.</p>',
                confirmButtonColor: '#2c7a7b',
            });
        }
    }

    window.addEventListener('beforeinstallprompt', function (e) {
        e.preventDefault();
        deferredPrompt = e;
        showInstallButton();
    });

    window.addEventListener('appinstalled', function () {
        deferredPrompt = null;
        hideInstallButton();
    });

    function bindUi() {
        if (isStandalone()) {
            hideInstallButton();
            return;
        }

        var btn = getBtn();
        if (!btn) {
            return;
        }

        if (isIosSafariInstallable()) {
            showInstallButton();
        }

        btn.addEventListener('click', onInstallClick);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindUi);
    } else {
        bindUi();
    }
})();
