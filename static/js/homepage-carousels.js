(function () {
    'use strict';

    function setupDragScroll(el) {
        if (!el || el._hpDrag) return;
        el._hpDrag = true;
        var isDown = false;
        var startX = 0;
        var scrollLeft = 0;
        var pointerId = null;
        // Mouse drag; touch uses native overflow-x swipe
        el.addEventListener('pointerdown', function (e) {
            if (e.pointerType !== 'mouse' || e.button !== 0) return;
            // Let segment live-card clicks open expand without drag capture
            if (e.target.closest('[data-hp-segment-open], a[href], button, [data-hp-stop-propagation]')) return;
            isDown = true;
            pointerId = e.pointerId;
            el.classList.add('is-dragging');
            startX = e.clientX;
            scrollLeft = el.scrollLeft;
            try { el.setPointerCapture(e.pointerId); } catch (err) {}
        });
        el.addEventListener('pointerup', function () {
            isDown = false;
            pointerId = null;
            el.classList.remove('is-dragging');
        });
        el.addEventListener('pointercancel', function () {
            isDown = false;
            pointerId = null;
            el.classList.remove('is-dragging');
        });
        el.addEventListener('pointermove', function (e) {
            if (!isDown || (pointerId != null && e.pointerId !== pointerId)) return;
            var dx = e.clientX - startX;
            if (Math.abs(dx) < 2) return;
            e.preventDefault();
            el.scrollLeft = scrollLeft - dx * 1.15;
        });
    }

    function setupPromoDots() {
        var slider = document.getElementById('hp-promo-slider');
        var dotsWrap = document.getElementById('hp-promo-dots');
        if (!slider || !dotsWrap) return;
        var slides = slider.querySelectorAll('.hp-promo-slide');
        if (!slides.length) return;
        dotsWrap.innerHTML = '';
        slides.forEach(function (_, idx) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.setAttribute('aria-label', 'Promo slide ' + (idx + 1));
            if (idx === 0) btn.className = 'active';
            btn.addEventListener('click', function () {
                var step = slides[0].offsetWidth + 16;
                slider.scrollTo({ left: idx * step, behavior: 'smooth' });
            });
            dotsWrap.appendChild(btn);
        });
        slider.addEventListener('scroll', function () {
            var step = slides[0].offsetWidth + 16;
            if (!step) return;
            var idx = Math.round(slider.scrollLeft / step);
            var dots = dotsWrap.querySelectorAll('button');
            dots.forEach(function (d, i) {
                d.classList.toggle('active', i === idx);
            });
        }, { passive: true });
    }

    function setupInsuranceServices() {
        var root = document.getElementById('hp-insurance-services');
        if (!root) return;
        var tabs = root.querySelectorAll('[data-hp-insurance-tabs] .hp-pill');
        var cards = root.querySelectorAll('[data-hp-insurance-cards] .hp-category-card');
        var cta = document.getElementById('hp-insurance-cta');
        if (!cta) return;
        var serviceType = 'New Policy';
        var tabId = 'buy';
        var selected = new Set();

        function syncTransferCards() {
            var isTransfer = tabId === 'transfer' || /port/i.test(serviceType);
            cards.forEach(function (card) {
                var t = card.getAttribute('data-insurance-type') || '';
                var isLife = /life/i.test(t);
                if (isTransfer && isLife) {
                    card.classList.add('d-none');
                    card.setAttribute('aria-pressed', 'false');
                    selected.delete(t);
                } else {
                    card.classList.remove('d-none');
                }
            });
        }

        function updateCta() {
            if (!selected.size) {
                cta.classList.remove('is-ready');
                cta.setAttribute('aria-disabled', 'true');
                return;
            }
            var base = '/find-agents?openFilter=1&ServiceType=' + encodeURIComponent(serviceType);
            selected.forEach(function (t) {
                base += '&InsuranceType=' + encodeURIComponent(t);
            });
            cta.href = base;
            cta.classList.add('is-ready');
            cta.removeAttribute('aria-disabled');
        }

        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                tabs.forEach(function (t) {
                    t.classList.remove('active');
                    t.setAttribute('aria-selected', 'false');
                });
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');
                serviceType = tab.getAttribute('data-service-type') || 'New Policy';
                tabId = tab.getAttribute('data-tab-id') || '';
                syncTransferCards();
                updateCta();
            });
        });

        cards.forEach(function (card) {
            card.addEventListener('click', function () {
                if (card.classList.contains('d-none')) return;
                var t = card.getAttribute('data-insurance-type');
                if (!t) return;
                if (selected.has(t)) {
                    selected.delete(t);
                    card.setAttribute('aria-pressed', 'false');
                } else {
                    selected.add(t);
                    card.setAttribute('aria-pressed', 'true');
                }
                updateCta();
            });
        });
        syncTransferCards();
    }

    function setupMutualFundServices() {
        var root = document.getElementById('hp-mutual-services');
        if (!root || root._hpMfReady) return;
        root._hpMfReady = true;
        var tabs = root.querySelectorAll('[data-hp-mutual-tabs] .hp-pill');
        var cards = root.querySelectorAll('[data-hp-mutual-cards] .hp-category-card');
        var cta = document.getElementById('hp-mutual-cta');
        if (!tabs.length || !cards.length || !cta) return;

        var activeTab = 'sip';
        var selected = new Set();

        function syncCards() {
            cards.forEach(function (card) {
                var tabsAttr = (card.getAttribute('data-mf-tabs') || '').toLowerCase();
                var visible = tabsAttr.split(/[\s,|]+/).indexOf(activeTab) !== -1;
                if (visible) {
                    card.hidden = false;
                    card.classList.remove('d-none');
                } else {
                    card.hidden = true;
                    card.classList.add('d-none');
                    card.setAttribute('aria-pressed', 'false');
                    selected.delete(card.getAttribute('data-mf-service') || '');
                }
            });
            updateCta();
        }

        function updateCta() {
            if (!selected.size) {
                cta.classList.add('hp-cta-btn--disabled');
                cta.classList.remove('is-ready');
                cta.setAttribute('aria-disabled', 'true');
                cta.href = '/find-agents?openFilter=1&InsuranceType=' + encodeURIComponent('Mutual Fund');
                return;
            }
            var base = '/find-agents?openFilter=1&InsuranceType=' + encodeURIComponent('Mutual Fund');
            var tab = root.querySelector('[data-hp-mutual-tabs] .hp-pill.active');
            var q = tab ? (tab.getAttribute('data-mf-query') || '') : '';
            if (q) base += '&ServiceType=' + encodeURIComponent(q);
            selected.forEach(function (s) {
                base += '&FundType=' + encodeURIComponent(s);
            });
            cta.href = base;
            cta.classList.remove('hp-cta-btn--disabled');
            cta.classList.add('is-ready');
            cta.removeAttribute('aria-disabled');
        }

        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                tabs.forEach(function (t) {
                    t.classList.remove('active');
                    t.setAttribute('aria-selected', 'false');
                });
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');
                activeTab = (tab.getAttribute('data-mf-tab') || 'sip').toLowerCase();
                selected.clear();
                syncCards();
            });
        });

        cards.forEach(function (card) {
            card.addEventListener('click', function () {
                if (card.hidden || card.classList.contains('d-none')) return;
                var service = card.getAttribute('data-mf-service') || '';
                if (!service) return;
                if (selected.has(service)) {
                    selected.delete(service);
                    card.setAttribute('aria-pressed', 'false');
                } else {
                    selected.add(service);
                    card.setAttribute('aria-pressed', 'true');
                }
                updateCta();
            });
        });

        syncCards();
    }

    function setupAutoScroll(selector, stepPx, intervalMs) {
        var scroller = document.querySelector(selector);
        if (!scroller || scroller._hpAuto) return;
        scroller._hpAuto = true;
        var timer = null;
        function tick() {
            if (scroller.scrollWidth <= scroller.clientWidth + 8) return;
            var max = scroller.scrollWidth - scroller.clientWidth;
            var next = scroller.scrollLeft + stepPx;
            if (next >= max - 1) next = 0;
            scroller.scrollLeft = next;
        }
        function start() { clearInterval(timer); timer = setInterval(tick, intervalMs); }
        function stop() { clearInterval(timer); }
        start();
        scroller.addEventListener('mouseenter', stop);
        scroller.addEventListener('mouseleave', start);
        scroller.addEventListener('touchstart', stop, { passive: true });
        scroller.addEventListener('touchend', function () { setTimeout(start, 2500); }, { passive: true });
    }

    function init() {
        document.querySelectorAll('[data-hp-carousel]').forEach(setupDragScroll);
        setupPromoDots();
        setupInsuranceServices();
        setupMutualFundServices();
        setupAutoScroll('[data-hp-carousel="matching"]', 1.1, 28);
        setupAutoScroll('[data-hp-carousel="promo"]', 0.45, 40);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    document.addEventListener('htmx:afterSettle', init);
})();