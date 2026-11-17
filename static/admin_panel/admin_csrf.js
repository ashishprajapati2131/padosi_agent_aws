/* Admin panel CSRF recovery.
 *
 * Admin pages embed {{ csrf_token }} when they render. If the padosi_csrf_token cookie changes
 * afterwards (another tab, a request that created a fresh cookie, the CSRF failure view), that
 * embedded token no longer matches and Django rejects the POST ("Your security session was
 * refreshed"). The cookie is always the current value, so every unsafe same-origin request uses
 * it, and a request that still fails with csrf_error is retried once with the fresh token.
 */
(function () {
    var UNSAFE = /^(POST|PUT|PATCH|DELETE)$/i;

    function csrfCookie() {
        var match = document.cookie.match(/(?:^|;\s*)padosi_csrf_token=([^;]*)/);
        return match ? decodeURIComponent(match[1]) : null;
    }

    function sameOrigin(url) {
        var link = document.createElement('a');
        link.href = url || window.location.href;
        return link.protocol + '//' + link.host === window.location.protocol + '//' + window.location.host;
    }

    // Plain form posts: refresh the hidden token just before submit.
    document.addEventListener('submit', function (e) {
        var form = e.target;
        var token = csrfCookie();
        if (!token || !form || (form.method || '').toUpperCase() !== 'POST' || !sameOrigin(form.action)) return;
        var input = form.querySelector('input[name="csrfmiddlewaretoken"]');
        if (input) input.value = token;
    }, true);

    if (window.jQuery) {
        var $ = window.jQuery;
        // Fires after per-call headers/beforeSend, so it replaces a stale embedded token.
        $(document).ajaxSend(function (_e, xhr, settings) {
            var token = csrfCookie();
            if (token && UNSAFE.test(settings.type) && sameOrigin(settings.url)) {
                xhr.setRequestHeader('X-CSRFToken', token);
            }
        });
        // One automatic retry when the server answers with a fresh token.
        $.ajaxPrefilter(function (options, original) {
            if (!UNSAFE.test(options.type) || original._csrfRetried || !sameOrigin(options.url)) return;
            var onError = options.error;
            options.error = function (xhr) {
                var data = xhr.responseJSON;
                if (xhr.status === 403 && data && data.csrf_error) {
                    $.ajax($.extend({}, original, { _csrfRetried: true }));
                    return;
                }
                if (onError) onError.apply(this, arguments);
            };
        });
    }

    if (window.fetch) {
        var originalFetch = window.fetch;
        window.fetch = function (url, options) {
            options = options || {};
            var target = typeof url === 'string' ? url : (url && url.url);
            if (!UNSAFE.test(options.method || 'GET') || !sameOrigin(target)) return originalFetch(url, options);
            var withToken = function () {
                var token = csrfCookie();
                var headers = new Headers(options.headers || {});
                if (token) headers.set('X-CSRFToken', token);
                return Object.assign({}, options, { headers: headers });
            };
            return originalFetch(url, withToken()).then(function (response) {
                if (response.status !== 403) return response;
                return response.clone().json().then(function (data) {
                    return data && data.csrf_error ? originalFetch(url, withToken()) : response;
                }, function () { return response; });
            });
        };
    }
})();
