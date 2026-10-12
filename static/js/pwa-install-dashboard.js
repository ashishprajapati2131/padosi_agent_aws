/**
 * Agent dashboard — Install PWA button (beforeinstallprompt + iOS Add to Home Screen).
 */
(function () {
    'use strict';

    var BTN_ID = 'pwaInstallAppBtn';
    var IOS_MODAL_ID = 'pwaInstallIosModal';
    var deferredPrompt = null;
    var hideTimer = null;
    var BLINK_DURATION_MS = 5000;

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
        if (!btn || isStandalone()) {
            return;
        }

        btn.classList.remove('d-none');
        btn.setAttribute('aria-hidden', 'false');
        btn.classList.add('pwa-btn-blink');
        btn.style.opacity = '1';
        btn.style.transition = 'opacity 0.5s ease, transform 0.5s ease';

        if (hideTimer) {
            clearTimeout(hideTimer);
        }

        // Stop blinking after 2-3 blinks (approx 2.7 seconds)
        setTimeout(function () {
            btn.classList.remove('pwa-btn-blink');
        }, 2700);

        // Then hide smoothly after a short pause (total ~4.5 seconds)
        hideTimer = setTimeout(function () {
            btn.classList.remove('pwa-btn-blink');
            btn.style.opacity = '0';
            btn.style.transform = 'scale(0.95)';
            setTimeout(function () {
                hideInstallButton();
                btn.style.opacity = '';
                btn.style.transform = '';
                btn.style.transition = '';
            }, 500);
        }, 4500);
    }

    function hideInstallButton() {
        var btn = getBtn();
        if (btn) {
            if (hideTimer) {
                clearTimeout(hideTimer);
                hideTimer = null;
            }
            btn.classList.remove('pwa-btn-blink');
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
        btn.addEventListener('mouseenter', function () {
            if (hideTimer) {
                clearTimeout(hideTimer);
                hideTimer = null;
            }
            btn.classList.remove('pwa-btn-blink');
            btn.style.opacity = '1';
        });
        btn.addEventListener('mouseleave', function () {
            if (!hideTimer && !btn.classList.contains('d-none')) {
                hideTimer = setTimeout(function () {
                    btn.style.opacity = '0';
                    btn.style.transform = 'scale(0.95)';
                    setTimeout(function () {
                        hideInstallButton();
                        btn.style.opacity = '';
                        btn.style.transform = '';
                        btn.style.transition = '';
                    }, 500);
                }, 2000);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindUi);
    } else {
        bindUi();
    }
})();
