/**
 * RegistrationCelebration — sparkler + confetti celebration overlay.
 * Isolated from business logic; invoked via RegistrationCelebration.show() or showRegCelebration().
 */
(function (window, document) {
    'use strict';

    var DEFAULT_DURATION_MS = 2500;
    var BURST_AT_MS = 1100;
    var CONFETTI_COLORS = ['#1e40af', '#0f766e', '#fbbf24', '#34d399', '#60a5fa', '#f472b6', '#a78bfa', '#fef08a', '#ffffff', '#059669'];
    var SPARK_COLORS = ['#fbbf24', '#fef08a', '#1e40af', '#60a5fa', '#0f766e', '#34d399', '#ffffff', '#059669', '#f472b6', '#a78bfa'];
    var STAR_COLORS = ['#fbbf24', '#60a5fa', '#34d399', '#ffffff', '#f472b6', '#fef08a'];
    var celebrationTimer = null;
    var burstTimer = null;
    var sparkInterval = null;

    function prefersReducedMotion() {
        return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function renderCelebrationName(nameEl, name) {
        if (!nameEl) return;
        var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
        if (!parts.length) {
            nameEl.style.display = 'none';
            nameEl.innerHTML = '';
            return;
        }
        nameEl.style.display = 'block';
        nameEl.innerHTML = parts.map(function (part) {
            return '<span class="name-part">' + escapeHtml(part) + '</span>';
        }).join(' ');
    }

    function clearParticles() {
        var confetti = document.getElementById('regCelebrationConfetti');
        var stars = document.getElementById('regCelebrationStars');
        var sparkField = document.getElementById('regCelebrationSparkField');
        if (confetti) confetti.innerHTML = '';
        if (stars) stars.innerHTML = '';
        if (sparkField) sparkField.innerHTML = '';
    }

    function spawnConfetti() {
        var field = document.getElementById('regCelebrationConfetti');
        if (!field || prefersReducedMotion()) return;

        for (var i = 0; i < 64; i++) {
            var piece = document.createElement('span');
            var color = CONFETTI_COLORS[i % CONFETTI_COLORS.length];
            var w = 4 + Math.floor(Math.random() * 7);
            var h = 3 + Math.floor(Math.random() * 9);
            var isCircle = Math.random() > 0.5;

            piece.className = 'reg-celeb-particle';
            piece.style.left = (Math.random() * 100) + '%';
            piece.style.background = color;
            piece.style.width = w + 'px';
            piece.style.height = (isCircle ? w : h) + 'px';
            piece.style.borderRadius = isCircle ? '50%' : '2px';
            piece.style.setProperty('--fall-dur', (1.6 + Math.random() * 1.6) + 's');
            piece.style.setProperty('--fall-delay', (Math.random() * 1.2) + 's');
            field.appendChild(piece);
        }
    }

    function spawnStars() {
        var field = document.getElementById('regCelebrationStars');
        if (!field || prefersReducedMotion()) return;

        for (var i = 0; i < 28; i++) {
            var star = document.createElement('span');
            star.className = 'reg-celeb-star';
            star.style.color = STAR_COLORS[i % STAR_COLORS.length];
            star.style.left = (10 + Math.random() * 80) + '%';
            star.style.top = (8 + Math.random() * 84) + '%';
            star.style.setProperty('--star-delay', (Math.random() * 1.1) + 's');
            if (Math.random() > 0.6) {
                star.style.fontSize = (8 + Math.random() * 6) + 'px';
            }
            field.appendChild(star);
        }
    }

    function createDynamicSpark(fromLeft) {
        var field = document.getElementById('regCelebrationSparkField');
        if (!field) return null;

        var el = document.createElement('span');
        var size = 3 + Math.floor(Math.random() * 5);
        var centerBand = 40 + Math.random() * 20;
        var travelX = (fromLeft ? 1 : -1) * (10 + Math.random() * 42);
        var travelY = -(40 + Math.random() * 100);
        var color = SPARK_COLORS[Math.floor(Math.random() * SPARK_COLORS.length)];
        var isStreak = Math.random() > 0.68;
        var isLarge = !isStreak && Math.random() > 0.82;

        el.className = 'reg-spark reg-spark--' + (isStreak ? 'streak' : (isLarge ? 'large' : 'static'));
        if (!isStreak) {
            el.style.width = size + 'px';
            el.style.height = size + 'px';
        }
        el.style.color = color;
        el.style.background = color;
        if (fromLeft) {
            el.style.left = centerBand + '%';
            el.style.right = 'auto';
        } else {
            el.style.right = (100 - centerBand) + '%';
            el.style.left = 'auto';
        }
        el.style.top = (40 + Math.random() * 18) + '%';
        el.style.setProperty('--tx', travelX + 'px');
        el.style.setProperty('--ty', travelY + 'px');
        if (isStreak) {
            el.style.setProperty('--rot', (fromLeft ? 1 : -1) * (10 + Math.random() * 30) + 'deg');
        }
        el.style.animationDelay = (Math.random() * 0.4) + 's';
        el.style.animationDuration = (0.65 + Math.random() * 0.55) + 's';
        field.appendChild(el);
        return el;
    }

    function spawnDynamicSparks() {
        if (prefersReducedMotion()) return;

        var total = 72;
        for (var i = 0; i < total; i++) {
            createDynamicSpark(i % 2 === 0);
        }

        for (var j = 0; j < 24; j++) {
            var halo = createDynamicSpark(j % 2 === 0);
            if (!halo) continue;
            halo.style.left = '50%';
            halo.style.right = 'auto';
            halo.style.top = (44 + Math.random() * 12) + '%';
            var angle = (j / 24) * Math.PI * 2;
            var radius = 50 + Math.random() * 60;
            halo.style.setProperty('--tx', Math.cos(angle) * radius + 'px');
            halo.style.setProperty('--ty', Math.sin(angle) * radius * 0.5 + 'px');
            halo.style.animationDelay = (0.1 + j * 0.04) + 's';
        }
    }

    function startSparkStream() {
        if (prefersReducedMotion()) return;
        var count = 0;
        sparkInterval = window.setInterval(function () {
            createDynamicSpark(count % 2 === 0);
            if (count % 3 === 0) createDynamicSpark(count % 2 !== 0);
            count += 1;
            var field = document.getElementById('regCelebrationSparkField');
            if (field && field.children.length > 140) {
                field.removeChild(field.firstChild);
            }
        }, 90);
    }

    function stopSparkStream() {
        if (sparkInterval) {
            clearInterval(sparkInterval);
            sparkInterval = null;
        }
    }

    function clearTimers() {
        if (celebrationTimer) {
            clearTimeout(celebrationTimer);
            celebrationTimer = null;
        }
        if (burstTimer) {
            clearTimeout(burstTimer);
            burstTimer = null;
        }
        stopSparkStream();
    }

    function hideOverlay(overlay, onComplete) {
        if (!overlay) {
            if (typeof onComplete === 'function') onComplete();
            return;
        }

        overlay.classList.remove('is-burst');
        overlay.classList.add('is-closing');

        window.setTimeout(function () {
            overlay.classList.remove('is-open', 'is-closing', 'is-burst');
            overlay.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('reg-celebration-active');
            clearParticles();
            if (typeof onComplete === 'function') onComplete();
        }, prefersReducedMotion() ? 0 : 320);
    }

    window.RegistrationCelebration = {
        show: function (options) {
            options = options || {};
            var overlay = document.getElementById('regCelebrationOverlay');
            var nameEl = document.getElementById('regCelebrationName');
            var msgEl = document.getElementById('regCelebrationMsg');
            var nextEl = document.getElementById('regCelebrationNext');
            var onComplete = typeof options.onComplete === 'function' ? options.onComplete : null;
            var redirectUrl = options.redirectUrl || '';
            var duration = typeof options.duration === 'number' ? options.duration : DEFAULT_DURATION_MS;

            if (prefersReducedMotion()) {
                duration = Math.min(duration, 900);
            }

            clearTimers();
            clearParticles();

            renderCelebrationName(nameEl, options.name || '');
            if (msgEl) msgEl.textContent = options.message || 'You\'re all set! Preview your digital card and profile website next.';
            if (nextEl) nextEl.textContent = options.nextText || 'Preparing your preview…';

            spawnConfetti();
            spawnStars();
            spawnDynamicSparks();
            startSparkStream();

            document.body.classList.add('reg-celebration-active');
            if (overlay) {
                overlay.classList.remove('is-closing');
                overlay.classList.add('is-open');
                overlay.setAttribute('aria-hidden', 'false');

                burstTimer = window.setTimeout(function () {
                    overlay.classList.add('is-burst');
                }, prefersReducedMotion() ? 0 : BURST_AT_MS);
            }

            celebrationTimer = window.setTimeout(function () {
                celebrationTimer = null;
                stopSparkStream();
                hideOverlay(overlay, function () {
                    if (onComplete) {
                        onComplete();
                    } else if (redirectUrl) {
                        window.location.href = redirectUrl;
                    }
                });
            }, duration);
        },

        hide: function () {
            var overlay = document.getElementById('regCelebrationOverlay');
            clearTimers();
            hideOverlay(overlay, null);
        }
    };

    window.showRegCelebration = function (name, options) {
        options = options || {};
        options.name = name;
        window.RegistrationCelebration.show(options);
    };
}(window, document));
