/* Pre-drafted messages in 23 languages (English + 22 scheduled Indian languages).
 *
 * PadosiMsgLang.translate(text, langs)  -> Promise<{code: text}> via /message-translate/
 * PadosiMsgLang.picker(select, opts)    share-time language dropdown
 * Editors ([data-msg-lang-editor], from {% message_lang_editor %}) start by themselves.
 */
(function () {
    if (window.PadosiMsgLang) return;

    var BATCH = 8; // server limit per call
    var memo = {};

    function csrfToken() {
        var m = document.cookie.match(/(?:^|;\s*)padosi_csrf_token=([^;]+)/);
        if (m) return decodeURIComponent(m[1]);
        var input = document.querySelector('input[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    function languages() {
        return window.PADOSI_MSG_LANGS || [];
    }

    function nameOf(code) {
        var lang = languages().filter(function (l) { return l.code === code; })[0];
        return lang ? lang.name : code;
    }

    // The WAF blocks "{{...}}" in non-admin requests, so send {{x}} as {__x__} and turn it back after.
    function encodePlaceholders(text) {
        return text.replace(/\{\{\s*(\w+)\s*\}\}/g, '{__$1__}');
    }
    function decodePlaceholders(text) {
        return text.replace(/\{__(\w+)__\}/g, '{{$1}}');
    }

    function postBatch(text, langs) {
        return fetch(window.PADOSI_MSG_TRANSLATE_URL || '/message-translate/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ text: encodePlaceholders(text), langs: langs })
        }).then(function (res) {
            return res.json().catch(function () { return {}; }).then(function (data) {
                if (!res.ok || !data.ok) throw new Error(data.error || 'Translation failed. Please try again.');
                var out = {};
                Object.keys(data.translations || {}).forEach(function (code) {
                    out[code] = decodePlaceholders(data.translations[code]);
                });
                return out;
            });
        });
    }

    function translate(text, langs) {
        text = (text || '').trim();
        var out = {};
        var need = [];
        langs.forEach(function (code) {
            var hit = memo[code + '|' + text];
            if (hit) out[code] = hit; else need.push(code);
        });
        if (!text || !need.length) return Promise.resolve(out);
        var batches = [];
        for (var i = 0; i < need.length; i += BATCH) batches.push(need.slice(i, i + BATCH));
        return Promise.all(batches.map(function (b) { return postBatch(text, b); })).then(function (parts) {
            parts.forEach(function (part) {
                Object.keys(part).forEach(function (code) {
                    memo[code + '|' + text] = part[code];
                    out[code] = part[code];
                });
            });
            return out;
        });
    }

    /* Share-time dropdown.
     * opts.base()             -> the message to translate (placeholders allowed)
     * opts.stored(code)       -> a saved text for that language, or a falsy value
     * opts.apply(text, code)  -> put the text in place
     * opts.onError(message)   -> optional
     */
    function picker(select, opts) {
        if (!select || select.dataset.msgLangReady) return;
        select.dataset.msgLangReady = '1';
        select.addEventListener('change', function () {
            var code = select.value;
            var saved = opts.stored ? opts.stored(code) : null;
            if (saved || code === 'en') {
                opts.apply(saved || opts.base(), code);
                return;
            }
            select.disabled = true;
            select.setAttribute('aria-busy', 'true');
            translate(opts.base(), [code]).then(function (t) {
                if (t[code]) {
                    opts.apply(t[code], code);
                } else {
                    opts.apply(opts.base(), code);
                    if (opts.onError) opts.onError('Could not translate to ' + nameOf(code) + '. Showing the original message.');
                }
            }).catch(function (err) {
                opts.apply(opts.base(), code);
                if (opts.onError) opts.onError(err.message);
            }).then(function () {
                select.disabled = false;
                select.removeAttribute('aria-busy');
            });
        });
    }

    function initEditor(box) {
        if (box.dataset.msgLangReady) return;
        box.dataset.msgLangReady = '1';
        var store = box.querySelector('[data-msg-lang-store]');
        var pick = box.querySelector('[data-msg-lang-pick]');
        var area = box.querySelector('[data-msg-lang-text]');
        var btn = box.querySelector('[data-msg-lang-translate]');
        var status = box.querySelector('[data-msg-lang-status]');
        var map = {};
        try { map = JSON.parse(store.value || '{}') || {}; } catch (e) { map = {}; }

        function setStatus(msg, isError) {
            status.textContent = msg || '';
            status.classList.toggle('is-error', !!isError);
        }
        function save() {
            store.value = JSON.stringify(map);
            store.dispatchEvent(new Event('change', { bubbles: true }));
        }
        function show() {
            area.value = map[pick.value] || '';
            var count = Object.keys(map).length;
            setStatus(count ? count + ' of ' + pick.options.length + ' languages ready.' : '');
        }
        function source() {
            var el = document.getElementById(box.dataset.source);
            return el ? el.value.trim() : '';
        }

        pick.addEventListener('change', show);
        area.addEventListener('input', function () {
            if (area.value.trim()) map[pick.value] = area.value; else delete map[pick.value];
            save();
        });
        btn.addEventListener('click', function () {
            var text = source();
            if (!text) {
                setStatus('Write the main message first, then translate it.', true);
                return;
            }
            if (Object.keys(map).length && !window.confirm('Replace the translations you already have?')) return;
            var codes = Array.prototype.map.call(pick.options, function (o) { return o.value; });
            btn.disabled = true;
            setStatus('Translating into ' + codes.length + ' languages… this can take up to a minute.');
            translate(text, codes).then(function (t) {
                Object.keys(t).forEach(function (code) { map[code] = t[code]; });
                save();
                show();
                var missing = codes.filter(function (c) { return !t[c]; });
                if (missing.length === codes.length) {
                    setStatus('Auto-translate is not available right now. Please try again later, or type the translations yourself.', true);
                    return;
                }
                setStatus(missing.length
                    ? 'Translated ' + (codes.length - missing.length) + ' of ' + codes.length + '. Not done: ' + missing.map(nameOf).join(', ') + '. Press again or type them.'
                    : 'Translated into all ' + codes.length + ' languages. Check them, then Save.', missing.length > 0);
            }).catch(function (err) {
                setStatus(err.message, true);
            }).then(function () {
                btn.disabled = false;
            });
        });
        show();
    }

    function initEditors(root) {
        (root || document).querySelectorAll('[data-msg-lang-editor]').forEach(initEditor);
    }

    window.PadosiMsgLang = { translate: translate, picker: picker, initEditors: initEditors, nameOf: nameOf };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { initEditors(); });
    } else {
        initEditors();
    }
})();
