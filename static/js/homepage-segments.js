(function () {
    'use strict';

    var COMPARE_ROWS = [
        { key: 'photo', label: 'Photo', type: 'photo' },
        { key: 'name', label: 'Name' },
        { key: 'match_score', label: 'Match %', fmt: function (v) { return v != null ? v + '%' : '—'; } },
        { key: 'rating', label: 'Rating' },
        { key: 'experience_display', label: 'Experience' },
        { key: 'happy_clients', label: 'Clients', fmt: function (v) { return v != null ? String(v) : '—'; } },
        { key: 'claims_settled', label: 'Claims settled', fmt: function (v) { return v ? v + '+' : '—'; } },
        { key: 'distance_display', label: 'Distance' },
        { key: 'license', label: 'IRDAI / ARN', fmt: function (_, a) {
            if (a.arn_number) return 'ARN ' + a.arn_number;
            if (a.license_number) return 'IRDAI ' + a.license_number;
            return '—';
        }},
        { key: 'actions', label: 'Contact', type: 'actions' }
    ];

    function el(id) { return document.getElementById(id); }

    function openModal(modal) {
        if (!modal) return;
        modal.removeAttribute('hidden');
        document.body.style.overflow = 'hidden';
    }

    function closeModal(modal) {
        if (!modal) return;
        modal.setAttribute('hidden', 'hidden');
        document.body.style.overflow = '';
    }

    function cellValue(row, agent) {
        if (row.type === 'photo') {
            var img = document.createElement('img');
            img.className = 'hp-compare-photo';
            img.alt = '';
            img.src = agent.profile_photo || '/static/img/avatar-icon.jpg';
            img.loading = 'lazy';
            return img;
        }
        if (row.type === 'actions') {
            var wrap = document.createElement('div');
            wrap.className = 'hp-compare-actions';
            if (agent.phone_url) {
                var call = document.createElement('a');
                call.href = agent.phone_url;
                call.textContent = 'Call';
                wrap.appendChild(call);
            }
            if (agent.whatsapp_url) {
                var wa = document.createElement('a');
                wa.href = agent.whatsapp_url;
                wa.target = '_blank';
                wa.rel = 'noopener noreferrer';
                wa.textContent = 'WhatsApp';
                wrap.appendChild(wa);
            }
            if (agent.profile_url) {
                var prof = document.createElement('a');
                prof.href = agent.profile_url;
                prof.textContent = 'Profile';
                wrap.appendChild(prof);
            }
            return wrap;
        }
        var raw = agent[row.key];
        if (row.fmt) return document.createTextNode(row.fmt(raw, agent));
        return document.createTextNode(raw != null && raw !== '' ? String(raw) : '—');
    }

    function renderCompareTable(agents) {
        var table = document.createElement('table');
        table.className = 'hp-compare-table hp-compare-table--h';
        var thead = document.createElement('thead');
        var headRow = document.createElement('tr');
        headRow.appendChild(document.createElement('th'));
        agents.forEach(function (a) {
            var th = document.createElement('th');
            th.textContent = a.name || 'Expert';
            headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);
        var tbody = document.createElement('tbody');
        COMPARE_ROWS.forEach(function (row) {
            var tr = document.createElement('tr');
            var label = document.createElement('td');
            label.textContent = row.label;
            tr.appendChild(label);
            agents.forEach(function (agent) {
                var td = document.createElement('td');
                var content = cellValue(row, agent);
                if (content && content.nodeType) td.appendChild(content);
                else td.textContent = content;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        return table;
    }

    function normalizeExpandAgent(a) {
        if (!a) return null;
        var match = a.match_score != null ? a.match_score : a.match_percent;
        var clients = a.happy_clients != null ? a.happy_clients : (a.clients_display || '—');
        var claims = a.claims_settled != null
            ? (String(a.claims_settled).indexOf('+') >= 0 ? a.claims_settled : a.claims_settled + '+')
            : (a.claims_display || '—');
        var license = a.license_line || '';
        if (!license) {
            if (a.arn_number) license = 'ARN ' + a.arn_number;
            else if (a.license_number) license = 'IRDAI ' + a.license_number;
        }
        return {
            name: a.name || 'Expert',
            photo: a.profile_photo || a.photo || '/static/img/avatar-icon.webp',
            is_verified: !!(a.is_verified || a.is_trusted),
            match_label: match != null && match !== '' ? match + '% Match' : '',
            distance: a.distance_display || '',
            location_line: a.location_line || '',
            experience_display: a.experience_display || '—',
            clients: clients,
            claims: claims,
            license: license,
            phone_url: a.phone_url || '',
            whatsapp_url: a.whatsapp_url || '',
            profile_url: a.profile_url || '',
            // keep API fields for compare table
            profile_photo: a.profile_photo || a.photo || '',
            match_score: match,
            happy_clients: a.happy_clients != null ? a.happy_clients : null,
            claims_settled: a.claims_settled != null ? a.claims_settled : null,
            distance_display: a.distance_display || '',
            arn_number: a.arn_number || '',
            license_number: a.license_number || '',
            rating: a.rating,
            experience_display_raw: a.experience_display || '—'
        };
    }

    function readEmbeddedAgents(segment) {
        var node = document.querySelector('[data-hp-segment-json="' + segment + '"]');
        if (!node) return [];
        try {
            var raw = JSON.parse(node.textContent || '[]');
            return Array.isArray(raw) ? raw.map(normalizeExpandAgent).filter(Boolean) : [];
        } catch (e) {
            return [];
        }
    }

    function renderExpandCards(agents) {
        var list = el('hp-segment-expand-list');
        if (!list) return;
        list.innerHTML = '';
        agents.forEach(function (raw) {
            var a = normalizeExpandAgent(raw) || raw;
            var card = document.createElement('div');
            card.className = 'hp-expand-card';
            var metaBits = [];
            if (a.match_label) metaBits.push(a.match_label);
            if (a.distance) metaBits.push(a.distance);
            else if (a.location_line) metaBits.push(a.location_line);
            card.innerHTML =
                '<div class="hp-expand-card-top">' +
                '<img src="' + (a.photo || '/static/img/avatar-icon.webp') + '" alt="" class="hp-expand-photo" loading="lazy">' +
                '<div><strong>' + (a.name || 'Expert') + '</strong>' +
                (a.is_verified ? ' <span class="hp-live-verified">✓</span>' : '') +
                '<p class="hp-expand-meta">' + metaBits.join(' · ') + '</p></div></div>' +
                '<div class="hp-expand-stats"><span><b>' + (a.experience_display || '—') + '</b> Exp</span><span><b>' + (a.clients || '—') + '</b> Clients</span><span><b>' + (a.claims || '—') + '</b> Claims</span></div>' +
                (a.license ? '<p class="hp-expand-license">' + a.license + '</p>' : '') +
                '<div class="hp-expand-actions">' +
                (a.phone_url ? '<a class="hp-live-btn hp-live-btn--call" href="' + a.phone_url + '">Call Now</a>' : '') +
                (a.whatsapp_url ? '<a class="hp-live-btn hp-live-btn--wa" href="' + a.whatsapp_url + '" target="_blank" rel="noopener noreferrer">WhatsApp</a>' : '') +
                '</div>';
            list.appendChild(card);
        });
    }

    function setupLocationFlow(section) {
        if (!section) return;

        var pinModal = el('hp-pin-modal');
        var saveUrl = section.getAttribute('data-save-location-url') || '/api/save-location/';
        var csrf = section.getAttribute('data-csrf') || '';
        var geoBusy = false;
        var hasLocation = section.getAttribute('data-has-location') === '1';

        function saveAndReload(payload) {
            return fetch(saveUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf
                },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            }).then(function (res) {
                if (!res.ok) throw new Error('save failed');
                try { sessionStorage.setItem('padosi_location_reloaded', '1'); } catch (e) {}
                window.location.reload();
            });
        }

        function requestBrowserGeo(fromButton) {
            if (!('geolocation' in navigator)) {
                openModal(pinModal);
                return;
            }
            if (geoBusy) return;
            geoBusy = true;
            var allowBtn = el('hp-geo-allow');
            if (allowBtn && fromButton) allowBtn.textContent = 'Detecting…';
            navigator.geolocation.getCurrentPosition(
                function (pos) {
                    geoBusy = false;
                    localStorage.setItem('padosi_location_status', 'granted');
                    localStorage.setItem('user_lat', String(pos.coords.latitude));
                    localStorage.setItem('user_lng', String(pos.coords.longitude));
                    localStorage.setItem('padosi_geo_expiry', String(Date.now() + 86400000));
                    saveAndReload({ lat: pos.coords.latitude, lng: pos.coords.longitude }).catch(function () {
                        openModal(pinModal);
                        if (allowBtn) allowBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg> Use Current Location';
                    });
                },
                function () {
                    geoBusy = false;
                    localStorage.setItem('padosi_location_status', 'denied');
                    openModal(pinModal);
                    if (allowBtn) allowBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg> Use Current Location';
                },
                { timeout: 10000, maximumAge: 300000, enableHighAccuracy: false }
            );
        }

        var allowBtn = el('hp-geo-allow');
        if (allowBtn) {
            allowBtn.addEventListener('click', function () {
                requestBrowserGeo(true);
            });
        }

        document.querySelectorAll('[data-hp-pin-close]').forEach(function (node) {
            node.addEventListener('click', function () { closeModal(pinModal); });
        });
        document.querySelectorAll('[data-hp-open-location], [data-hp-open-pin]').forEach(function (node) {
            node.addEventListener('click', function (e) {
                e.preventDefault();
                openModal(pinModal);
            });
        });

        var form = el('hp-pin-form');
        function submitPin() {
            var input = el('hp-pin-input');
            var err = el('hp-pin-error');
            var pin = (input && input.value || '').trim();
            if (!/^[1-9]\d{5}$/.test(pin)) {
                if (err) { err.textContent = 'Enter a valid 6-digit PIN'; err.hidden = false; }
                return;
            }
            if (err) err.hidden = true;
            saveAndReload({ pincode: pin }).catch(function () {
                if (err) { err.textContent = 'Could not save PIN. Try again.'; err.hidden = false; }
            });
        }
        if (form) {
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                submitPin();
            });
        }
        var pinInput = el('hp-pin-input');
        if (pinInput) {
            pinInput.addEventListener('input', function () {
                var digits = pinInput.value.replace(/\D/g, '').slice(0, 6);
                pinInput.value = digits;
                if (digits.length === 6) submitPin();
            });
        }

        // First home visit without location: ask browser GPS; PIN modal only on deny/error
        if (hasLocation) return;
        var skipKey = 'hp_loc_prompted';
        var already = false;
        try { already = sessionStorage.getItem(skipKey) === '1'; } catch (e) {}
        if (!already) {
            try { sessionStorage.setItem(skipKey, '1'); } catch (e) {}
            setTimeout(function () { requestBrowserGeo(false); }, 350);
        }
    }

    function setupSegmentUi() {
        var section = document.getElementById('hp-segment-experts');
        if (!section) return;

        setupLocationFlow(section);

        var compareUrl = section.getAttribute('data-segment-compare-url') || '/home/segment-compare/';
        var expandModal = el('hp-segment-expand-modal');
        var compareModal = el('hp-segment-compare-modal');
        var currentSegment = '';
        var currentAgents = [];
        var currentUrl = '/find-agents?openFilter=1';

        function fetchSegmentAgents(segment) {
            return fetch(compareUrl + '?segment=' + encodeURIComponent(segment), {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin'
            }).then(function (res) {
                return res.json().then(function (body) {
                    return { ok: res.ok, body: body };
                });
            });
        }

        function openExpand(segment, title, moreUrl) {
            currentSegment = segment;
            currentUrl = moreUrl || '/find-agents?openFilter=1';
            var titleEl = el('hp-segment-expand-title');
            if (titleEl) titleEl.textContent = title || 'Top experts';
            var more = el('hp-expand-more');
            if (more) more.href = currentUrl;
            var list = el('hp-segment-expand-list');
            var embedded = readEmbeddedAgents(segment);
            openModal(expandModal);
            if (embedded.length) {
                currentAgents = embedded;
                renderExpandCards(embedded);
            } else if (list) {
                list.innerHTML = '<p class="hp-segment-modal-loading">Loading…</p>';
            }
            fetchSegmentAgents(segment).then(function (result) {
                if (!result.ok || !result.body.success) {
                    if (!embedded.length && list) {
                        list.innerHTML = '<p class="text-danger">' + ((result.body && result.body.message) || 'No experts found') + '</p>';
                    }
                    if (!embedded.length) currentAgents = [];
                    return;
                }
                currentAgents = result.body.agents || [];
                renderExpandCards(currentAgents);
            }).catch(function () {
                if (!embedded.length && list) {
                    list.innerHTML = '<p class="text-danger">Network error. Try again.</p>';
                }
            });
        }

        function openCompare(segment) {
            var loadingEl = el('hp-segment-compare-loading');
            var errorEl = el('hp-segment-compare-error');
            var tableWrap = el('hp-segment-compare-table');
            var titleEl = el('hp-segment-compare-title');
            if (loadingEl) loadingEl.hidden = false;
            if (errorEl) { errorEl.hidden = true; errorEl.textContent = ''; }
            if (tableWrap) { tableWrap.hidden = true; tableWrap.innerHTML = ''; }
            if (titleEl) titleEl.textContent = 'Compare best 3 experts';
            openModal(compareModal);

            function paint(agents) {
                if (loadingEl) loadingEl.hidden = true;
                if (!agents || !agents.length) {
                    if (errorEl) { errorEl.textContent = 'No experts to compare.'; errorEl.hidden = false; }
                    return;
                }
                if (tableWrap) {
                    tableWrap.appendChild(renderCompareTable(agents));
                    tableWrap.hidden = false;
                }
            }

            if (currentSegment === segment && currentAgents.length) {
                paint(currentAgents);
                return;
            }
            fetchSegmentAgents(segment).then(function (result) {
                if (!result.ok || !result.body.success) {
                    if (loadingEl) loadingEl.hidden = true;
                    if (errorEl) {
                        errorEl.textContent = (result.body && result.body.message) || 'Could not load experts.';
                        errorEl.hidden = false;
                    }
                    return;
                }
                currentAgents = result.body.agents || [];
                paint(currentAgents);
            }).catch(function () {
                if (loadingEl) loadingEl.hidden = true;
                if (errorEl) { errorEl.textContent = 'Network error. Try again.'; errorEl.hidden = false; }
            });
        }

        function openFromCard(card) {
            if (!card) return;
            openExpand(
                card.getAttribute('data-hp-segment-open'),
                card.getAttribute('data-hp-segment-title') || 'Top experts',
                card.getAttribute('data-hp-segment-url')
            );
        }

        // Bind directly on live stacks so carousel drag does not swallow the open action
        section.querySelectorAll('[data-hp-segment-open]').forEach(function (card) {
            var startX = 0;
            var startY = 0;
            var moved = false;
            card.addEventListener('pointerdown', function (e) {
                if (e.target.closest('[data-hp-stop-propagation], a[href], button')) return;
                startX = e.clientX;
                startY = e.clientY;
                moved = false;
            });
            card.addEventListener('pointermove', function (e) {
                if (Math.abs(e.clientX - startX) > 8 || Math.abs(e.clientY - startY) > 8) moved = true;
            });
            card.addEventListener('click', function (e) {
                if (e.target.closest('[data-hp-stop-propagation], a[href], button')) return;
                if (moved) return;
                e.preventDefault();
                e.stopPropagation();
                openFromCard(card);
            });
            card.addEventListener('keydown', function (e) {
                if (e.key !== 'Enter' && e.key !== ' ') return;
                e.preventDefault();
                openFromCard(card);
            });
        });

        var compareBtn = el('hp-expand-compare');
        if (compareBtn) {
            compareBtn.addEventListener('click', function () {
                closeModal(expandModal);
                openCompare(currentSegment);
            });
        }

        document.querySelectorAll('[data-hp-expand-close]').forEach(function (node) {
            node.addEventListener('click', function () { closeModal(expandModal); });
        });
        document.querySelectorAll('[data-hp-modal-close]').forEach(function (node) {
            node.addEventListener('click', function () { closeModal(compareModal); });
        });
        document.addEventListener('keydown', function (e) {
            if (e.key !== 'Escape') return;
            closeModal(expandModal);
            closeModal(compareModal);
            closeModal(el('hp-pin-modal'));
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setupSegmentUi);
    } else {
        setupSegmentUi();
    }
})();