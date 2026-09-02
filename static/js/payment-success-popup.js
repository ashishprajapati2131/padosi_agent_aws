/**
 * Branded 3-second payment success popup → dashboard redirect.
 */
(function (window) {
    'use strict';

    var DEFAULT_MS = 3000;

    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function buildHtml(agentName) {
        var safeName = escapeHtml(agentName);
        var nameBlock = safeName
            ? '<h3 class="pay-success-name">Welcome, ' + safeName + '!</h3>'
            : '<h3 class="pay-success-name">You\'re all set!</h3>';

        return ''
            + '<div class="pay-success-popup">'
            + '  <div class="pay-success-popup__hero">'
            + '    <div class="pay-success-icon-wrap">'
            + '      <div class="pay-success-icon-ring"></div>'
            + '      <div class="pay-success-icon-circle"><i class="fa-solid fa-check"></i></div>'
            + '    </div>'
            + '    <p class="pay-success-kicker">Payment Successful</p>'
            +      nameBlock
            + '    <p class="pay-success-lead">Your account is activated and ready to use.</p>'
            + '  </div>'
            + '  <ul class="pay-success-notes">'
            + '    <li><i class="fa-solid fa-shield-halved"></i> Payment verified securely via Razorpay</li>'
            + '    <li><i class="fa-solid fa-file-invoice"></i> Invoice &amp; login details will be emailed shortly</li>'
            + '    <li><i class="fa-solid fa-gauge-high"></i> Opening your agent dashboard automatically</li>'
            + '  </ul>'
            + '  <div class="pay-success-footer">'
            + '    <i class="fa-solid fa-spinner fa-spin"></i>'
            + '    <span>Redirecting to dashboard…</span>'
            + '  </div>'
            + '</div>';
    }

    function showPaymentSuccessPopup(options) {
        options = options || {};
        var redirectUrl = options.redirectUrl || '/agent/dashboard/';
        var agentName = options.agentName || '';
        var duration = typeof options.duration === 'number' ? options.duration : DEFAULT_MS;

        function go() {
            window.location.replace(redirectUrl);
        }

        if (typeof window.Swal === 'undefined') {
            window.setTimeout(go, duration);
            return Promise.resolve();
        }

        return window.Swal.fire({
            html: buildHtml(agentName),
            customClass: { popup: 'payment-success-popup' },
            showConfirmButton: false,
            showCloseButton: false,
            allowOutsideClick: false,
            allowEscapeKey: false,
            timer: duration,
            timerProgressBar: true,
            backdrop: 'rgba(15, 23, 42, 0.45)',
            didOpen: function () {
                var popup = window.Swal.getPopup();
                if (popup) popup.setAttribute('aria-label', 'Payment successful');
            }
        }).then(go);
    }

    window.showPaymentSuccessPopup = showPaymentSuccessPopup;
}(window));
