
document.addEventListener('DOMContentLoaded', function() {
    // Social Channels Add / Delete
    const addSocialBtn = document.getElementById('addSocialChannelBtn');
    const socialContainer = document.getElementById('socialChannelsContainer');
    if (addSocialBtn && socialContainer) {
        addSocialBtn.addEventListener('click', function() {
            const row = document.createElement('div');
            row.className = 'row g-2 align-items-center social-channel-row p-2 border rounded bg-white';
            row.innerHTML = `
                <div class="col-md-3">
                    <div class="input-group input-group-sm">
                        <span class="input-group-text"><i class="fa-solid fa-tag"></i></span>
                        <input type="text" name="social_platform[]" class="form-control" placeholder="Platform (e.g. YouTube)">
                    </div>
                </div>
                <div class="col-md-8">
                    <div class="input-group input-group-sm">
                        <span class="input-group-text"><i class="fa-solid fa-globe"></i></span>
                        <input type="url" name="social_url[]" class="form-control" placeholder="https://youtube.com/@yourhandle">
                    </div>
                </div>
                <div class="col-md-1 text-center">
                    <button type="button" class="btn btn-sm btn-outline-danger w-100 delete-social-row-btn" title="Remove">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            `;
            socialContainer.appendChild(row);
        });

        socialContainer.addEventListener('click', function(e) {
            const delBtn = e.target.closest('.delete-social-row-btn');
            if (delBtn) {
                const row = delBtn.closest('.social-channel-row');
                if (socialContainer.querySelectorAll('.social-channel-row').length > 1) {
                    row.remove();
                } else {
                    row.querySelectorAll('input').forEach(inp => inp.value = '');
                }
            }
        });
    }

    // Scratch popup feature tiles Add / Delete
    const addScratchFeatureBtn = document.getElementById('addScratchFeatureBtn');
    const scratchFeaturesContainer = document.getElementById('scratchFeaturesContainer');
    if (addScratchFeatureBtn && scratchFeaturesContainer) {
        addScratchFeatureBtn.addEventListener('click', function() {
            const row = document.createElement('div');
            row.className = 'row g-2 align-items-center scratch-feature-row p-2 border rounded bg-white';
            row.innerHTML = `
                <div class="col-md-4">
                    <input type="text" name="sp_feature_name[]" class="form-control form-control-sm" placeholder="Feature name (HTML ok)">
                </div>
                <div class="col-md-2">
                    <input type="text" name="sp_feature_icon[]" class="form-control form-control-sm" value="fa-star" placeholder="fa-globe">
                </div>
                <div class="col-md-2">
                    <input type="color" name="sp_feature_color[]" class="form-control form-control-color w-100" value="#16a34a">
                </div>
                <div class="col-md-2">
                    <input type="color" name="sp_feature_bg_color[]" class="form-control form-control-color w-100" value="#f0fdf4">
                </div>
                <div class="col-md-2 text-end">
                    <button type="button" class="btn btn-sm btn-outline-danger delete-scratch-feature-btn"><i class="fa-solid fa-trash-can"></i></button>
                </div>
            `;
            scratchFeaturesContainer.appendChild(row);
        });

        scratchFeaturesContainer.addEventListener('click', function(e) {
            const delBtn = e.target.closest('.delete-scratch-feature-btn');
            if (!delBtn) return;
            const row = delBtn.closest('.scratch-feature-row');
            if (scratchFeaturesContainer.querySelectorAll('.scratch-feature-row').length > 1) {
                row.remove();
            } else {
                row.querySelectorAll('input[type="text"]').forEach(inp => inp.value = '');
            }
        });
    }

    function followBasePrice(plan) {
        if (plan === 'starter') {
            var scratchOn = document.getElementById('starterScratchSwitch');
            var scratchEl = document.getElementById('starterScratchPrice');
            var promoEl = document.getElementById('starterPromoPrice');
            var scratch = scratchEl ? parseFloat(scratchEl.value) : NaN;
            var promo = promoEl ? parseFloat(promoEl.value) : NaN;
            if (scratchOn && scratchOn.checked && !isNaN(scratch)) return scratch;
            return isNaN(promo) ? 0 : promo;
        }
        var scratchOn = document.getElementById('profScratchSwitch');
        var scratchEl = document.getElementById('proScratchPrice');
        var promoEl = document.getElementById('proPromoPrice');
        var scratch = scratchEl ? parseFloat(scratchEl.value) : NaN;
        var promo = promoEl ? parseFloat(promoEl.value) : NaN;
        if (scratchOn && scratchOn.checked && !isNaN(scratch)) return scratch;
        return isNaN(promo) ? 0 : promo;
    }

    function syncTierPriceFromDiscount(row, plan) {
        var discName = plan === 'starter' ? 'tier_starter_discount[]' : 'tier_prof_discount[]';
        var priceName = plan === 'starter' ? 'tier_starter_price[]' : 'tier_prof_price[]';
        var disc = row.querySelector('[name="' + discName + '"]');
        var price = row.querySelector('[name="' + priceName + '"]');
        if (!disc || !price) return;
        var off = parseFloat(disc.value);
        if (isNaN(off)) return;
        price.value = Math.max(0, Math.round(followBasePrice(plan) - off));
    }

    function syncTierDiscountFromPrice(row, plan) {
        var discName = plan === 'starter' ? 'tier_starter_discount[]' : 'tier_prof_discount[]';
        var priceName = plan === 'starter' ? 'tier_starter_price[]' : 'tier_prof_price[]';
        var disc = row.querySelector('[name="' + discName + '"]');
        var price = row.querySelector('[name="' + priceName + '"]');
        if (!disc || !price) return;
        var charged = parseFloat(price.value);
        if (isNaN(charged)) return;
        disc.value = Math.max(0, Math.round(followBasePrice(plan) - charged));
    }

    function refreshAllTierPricesFromDiscounts() {
        document.querySelectorAll('.tier-rule-row').forEach(function(row) {
            syncTierPriceFromDiscount(row, 'starter');
            syncTierPriceFromDiscount(row, 'professional');
        });
    }

    const followTiersTable = document.getElementById('followTiersTable');
    if (followTiersTable) {
        followTiersTable.addEventListener('input', function(e) {
            var row = e.target.closest('.tier-rule-row');
            if (row && e.target.name === 'tier_starter_discount[]') {
                syncTierPriceFromDiscount(row, 'starter');
            } else if (row && e.target.name === 'tier_prof_discount[]') {
                syncTierPriceFromDiscount(row, 'professional');
            } else if (row && e.target.name === 'tier_starter_price[]') {
                syncTierDiscountFromPrice(row, 'starter');
            } else if (row && e.target.name === 'tier_prof_price[]') {
                syncTierDiscountFromPrice(row, 'professional');
            }
        });
    }

    // Follow Tiers Add / Delete
    const addTierBtn = document.getElementById('addTierRuleBtn');
    const tiersContainer = document.getElementById('followTiersContainer');
    if (addTierBtn && tiersContainer) {
        addTierBtn.addEventListener('click', function() {
            const count = tiersContainer.querySelectorAll('.tier-rule-row').length + 1;
            const starterOff = count * 100;
            const profOff = count * 100;
            const starterPrice = Math.max(0, Math.round(followBasePrice('starter') - starterOff));
            const profPrice = Math.max(0, Math.round(followBasePrice('professional') - profOff));
            const tr = document.createElement('tr');
            tr.className = 'tier-rule-row';
            tr.innerHTML = `
                <td>
                    <div class="input-group input-group-sm">
                        <span class="input-group-text"><i class="fa-solid fa-user-check"></i></span>
                        <input type="number" name="tier_follows[]" class="form-control tier-input" value="${count}" min="1" max="10">
                    </div>
                    <small class="text-muted">accounts followed</small>
                </td>
                <td>
                    <div class="input-group input-group-sm">
                        <span class="input-group-text">₹</span>
                        <input type="number" name="tier_starter_discount[]" class="form-control tier-input" value="${starterOff}" min="0">
                    </div>
                    <small class="text-muted">Starter extra OFF</small>
                </td>
                <td>
                    <div class="input-group input-group-sm">
                        <span class="input-group-text">₹</span>
                        <input type="number" name="tier_starter_price[]" class="form-control tier-input" value="${starterPrice}" placeholder="Auto if blank">
                    </div>
                    <small class="text-muted">final Starter price, excl. GST</small>
                </td>
                <td>
                    <div class="input-group input-group-sm">
                        <span class="input-group-text">₹</span>
                        <input type="number" name="tier_prof_discount[]" class="form-control tier-input" value="${profOff}" min="0">
                    </div>
                    <small class="text-muted">Professional extra OFF</small>
                </td>
                <td>
                    <div class="input-group input-group-sm">
                        <span class="input-group-text">₹</span>
                        <input type="number" name="tier_prof_price[]" class="form-control tier-input" value="${profPrice}" placeholder="Auto if blank">
                    </div>
                    <small class="text-muted">final Professional price, excl. GST</small>
                </td>
                <td class="text-center">
                    <button type="button" class="btn btn-sm btn-outline-danger delete-tier-row-btn" title="Remove Tier">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </td>
            `;
            tiersContainer.appendChild(tr);
        });

        tiersContainer.addEventListener('click', function(e) {
            const delBtn = e.target.closest('.delete-tier-row-btn');
            if (delBtn) {
                const tr = delBtn.closest('.tier-rule-row');
                if (tiersContainer.querySelectorAll('.tier-rule-row').length > 1) {
                    tr.remove();
                } else {
                    tr.querySelectorAll('input').forEach(inp => inp.value = '');
                }
            }
        });
    }

    // Edit Profile Dependency Logic (Column-based)
    const masterInputs = document.querySelectorAll('input[value="edit_profile"]');
    const childValues = [
        'edit_profile_basic',
        'edit_profile_professional',
        'edit_profile_portfolio',
        'edit_profile_additional'
    ];
    
    function syncEditProfileChildren(masterInput) {
        const isChecked = masterInput.checked;
        const colName = masterInput.name; // e.g. features_starter[]
        
        childValues.forEach(val => {
            const childInput = document.querySelector(`input[name="${colName}"][value="${val}"]`);
            if (childInput) {
                childInput.disabled = !isChecked;
                if (!isChecked) {
                    childInput.closest('td').style.opacity = '0.4';
                } else {
                    childInput.closest('td').style.opacity = '1';
                }
            }
        });
    }

    masterInputs.forEach(master => {
        master.addEventListener('change', function() {
            syncEditProfileChildren(this);
        });
        syncEditProfileChildren(master); // Run on load
    });

    const qrMasterInputs = document.querySelectorAll('input[value="qr_codes"]');
    function syncQrChildren(masterInput) {
        const isChecked = masterInput.checked;
        const colName = masterInput.name;
        const childInput = document.querySelector('input[name="' + colName + '"][value="qr_poster_download"]');
        if (childInput) {
            childInput.disabled = !isChecked;
            if (!isChecked) {
                childInput.checked = false;
                childInput.closest('td').style.opacity = '0.4';
            } else {
                childInput.closest('td').style.opacity = '1';
            }
        }
    }
    qrMasterInputs.forEach(function(master) {
        master.addEventListener('change', function() {
            syncQrChildren(this);
        });
        syncQrChildren(master);
    });

    (function initUnlockRulesBuilder() {
        const dataEl = document.getElementById('unlock-builder-data');
        const listEl = document.getElementById('unlockRulesList');
        const formEl = document.getElementById('unlockRulesForm');
        const jsonEl = document.getElementById('unlockRulesJson');
        const addBtn = document.getElementById('addUnlockRuleBtn');
        if (!dataEl || !listEl || !formEl || !jsonEl || !addBtn) return;

        const builder = JSON.parse(dataEl.textContent);
        const features = builder.features || [];
        const metrics = builder.metrics || {};
        const plans = builder.plans || [];
        const opLabels = builder.opLabels || {};
        const segments = builder.segments || [];
        let rules = Array.isArray(builder.rules) ? builder.rules.slice() : [];

        function uid() {
            return 'rule_' + Date.now() + '_' + Math.floor(Math.random() * 1000);
        }

        function optionHtml(items, selected) {
            return items.map(function(item) {
                const key = item.key || item;
                const label = item.label || item;
                return '<option value="' + key + '"' + (key === selected ? ' selected' : '') + '>' + label + '</option>';
            }).join('');
        }

        function metricOptions(selected) {
            return Object.keys(metrics).map(function(key) {
                return '<option value="' + key + '"' + (key === selected ? ' selected' : '') + '>' + metrics[key].label + '</option>';
            }).join('');
        }

        function operatorOptions(metricKey, selected) {
            const spec = metrics[metricKey] || { operators: ['gte'], default_op: 'gte' };
            const ops = spec.operators || ['gte'];
            const current = selected || spec.default_op || ops[0];
            return ops.map(function(op) {
                return '<option value="' + op + '"' + (op === current ? ' selected' : '') + '>' + (opLabels[op] || op) + '</option>';
            }).join('');
        }

        function valueControl(metricKey, value) {
            const spec = metrics[metricKey] || { widget: 'number' };
            if (spec.widget === 'boolean') {
                const yes = value === true || value === 'true' || value === 1 || value === '1';
                return '<select class="form-select form-select-sm unlock-cond-value">' +
                    '<option value="true"' + (yes ? ' selected' : '') + '>Present</option>' +
                    '<option value="false"' + (!yes ? ' selected' : '') + '>Absent</option>' +
                    '</select>';
            }
            if (spec.widget === 'segment') {
                return '<select class="form-select form-select-sm unlock-cond-value">' + optionHtml(segments, value) + '</select>';
            }
            const min = spec.widget === 'percent' ? ' min="0" max="100"' : ' min="0"';
            const step = spec.widget === 'currency' ? ' step="0.01"' : ' step="1"';
            const val = (value === 0 || value) ? value : '';
            return '<input type="number" class="form-control form-control-sm unlock-cond-value" value="' + val + '"' + min + step + ' placeholder="Value">';
        }

        function defaultCondition() {
            return { metric: 'reviews', op: 'gte', value: 10 };
        }

        function defaultRule() {
            return {
                id: uid(),
                enabled: true,
                feature: features[0] ? features[0].key : '',
                plans: plans.map(function(p) { return p.key; }),
                match: 'all',
                conditions: [defaultCondition()]
            };
        }

        function renderCondition(cond) {
            const metric = cond.metric || 'reviews';
            return '<div class="unlock-cond-row">' +
                '<select class="form-select form-select-sm unlock-cond-metric">' + metricOptions(metric) + '</select>' +
                '<select class="form-select form-select-sm unlock-cond-op">' + operatorOptions(metric, cond.op) + '</select>' +
                '<div class="unlock-cond-value-wrap">' + valueControl(metric, cond.value) + '</div>' +
                '<button type="button" class="btn btn-sm btn-outline-danger unlock-remove-cond"><i class="fa-solid fa-trash"></i></button>' +
                '</div>';
        }

        function renderRule(rule, index) {
            const selectedPlans = rule.plans || [];
            const planChecks = plans.map(function(p) {
                const checked = selectedPlans.indexOf(p.key) !== -1 ? ' checked' : '';
                return '<label class="d-flex align-items-center gap-2 mb-0" style="font-size:12px;font-weight:600;">' +
                    '<input type="checkbox" class="form-check-input unlock-plan-check m-0" value="' + p.key + '"' + checked + '>' +
                    p.label + '</label>';
            }).join('');
            const conditions = (rule.conditions && rule.conditions.length) ? rule.conditions : [defaultCondition()];
            return '<div class="unlock-rule-card" data-rule-index="' + index + '">' +
                '<div class="unlock-rule-head">' +
                    '<div class="d-flex align-items-center gap-3">' +
                        '<div class="form-check form-switch m-0">' +
                            '<input class="form-check-input unlock-enabled" type="checkbox"' + (rule.enabled !== false ? ' checked' : '') + '>' +
                        '</div>' +
                        '<span class="fw-bold" style="font-size:13px;">Rule ' + (index + 1) + '</span>' +
                    '</div>' +
                    '<button type="button" class="btn btn-sm btn-outline-danger unlock-remove-rule"><i class="fa-solid fa-trash me-1"></i> Delete</button>' +
                '</div>' +
                '<div class="p-3">' +
                    '<div class="row g-3 mb-3">' +
                        '<div class="col-md-6">' +
                            '<label class="form-label fw-bold mb-1" style="font-size:12px;">Feature to unlock</label>' +
                            '<select class="form-select form-select-sm unlock-feature">' + optionHtml(features, rule.feature) + '</select>' +
                        '</div>' +
                        '<div class="col-md-6">' +
                            '<label class="form-label fw-bold mb-1" style="font-size:12px;">Match</label>' +
                            '<select class="form-select form-select-sm unlock-match">' +
                                '<option value="all"' + (rule.match !== 'any' ? ' selected' : '') + '>All conditions (AND)</option>' +
                                '<option value="any"' + (rule.match === 'any' ? ' selected' : '') + '>Any condition (OR)</option>' +
                            '</select>' +
                        '</div>' +
                    '</div>' +
                    '<label class="form-label fw-bold mb-2" style="font-size:12px;">Applies to plans</label>' +
                    '<div class="unlock-plan-pills mb-3">' + planChecks + '</div>' +
                    '<label class="form-label fw-bold mb-2" style="font-size:12px;">Conditions</label>' +
                    '<div class="unlock-conditions">' + conditions.map(renderCondition).join('') + '</div>' +
                    '<button type="button" class="btn btn-sm btn-outline-success unlock-add-cond mt-1"><i class="fa-solid fa-plus me-1"></i> Add condition</button>' +
                '</div>' +
            '</div>';
        }

        function render() {
            if (!rules.length) {
                listEl.innerHTML = '<p class="text-muted mb-3" style="font-size:13px;">No activity rules yet. Add a rule such as: 10 reviews AND 5 referrals → unlock Agent Certificate.</p>';
                return;
            }
            listEl.innerHTML = rules.map(renderRule).join('');
        }

        function readValue(wrap, metricKey) {
            const input = wrap.querySelector('.unlock-cond-value');
            if (!input) return '';
            const spec = metrics[metricKey] || {};
            if (spec.widget === 'boolean') return input.value === 'true';
            if (spec.widget === 'segment') return input.value;
            if (input.value === '') return '';
            return Number(input.value);
        }

        function collectFromDom() {
            const cards = listEl.querySelectorAll('.unlock-rule-card');
            const collected = [];
            cards.forEach(function(card, idx) {
                const condRows = card.querySelectorAll('.unlock-cond-row');
                const conditions = [];
                condRows.forEach(function(row) {
                    const metric = row.querySelector('.unlock-cond-metric').value;
                    conditions.push({
                        metric: metric,
                        op: row.querySelector('.unlock-cond-op').value,
                        value: readValue(row.querySelector('.unlock-cond-value-wrap'), metric)
                    });
                });
                const selectedPlans = [];
                card.querySelectorAll('.unlock-plan-check:checked').forEach(function(cb) {
                    selectedPlans.push(cb.value);
                });
                collected.push({
                    id: (rules[idx] && rules[idx].id) || uid(),
                    enabled: card.querySelector('.unlock-enabled').checked,
                    feature: card.querySelector('.unlock-feature').value,
                    match: card.querySelector('.unlock-match').value,
                    plans: selectedPlans,
                    conditions: conditions
                });
            });
            rules = collected;
            return collected;
        }

        listEl.addEventListener('click', function(e) {
            const addCond = e.target.closest('.unlock-add-cond');
            const removeCond = e.target.closest('.unlock-remove-cond');
            const removeRule = e.target.closest('.unlock-remove-rule');
            if (addCond) {
                collectFromDom();
                const card = addCond.closest('.unlock-rule-card');
                const idx = Number(card.getAttribute('data-rule-index'));
                rules[idx].conditions = rules[idx].conditions || [];
                rules[idx].conditions.push(defaultCondition());
                render();
            } else if (removeCond) {
                collectFromDom();
                const card = removeCond.closest('.unlock-rule-card');
                const row = removeCond.closest('.unlock-cond-row');
                const idx = Number(card.getAttribute('data-rule-index'));
                const rows = Array.prototype.slice.call(card.querySelectorAll('.unlock-cond-row'));
                const condIdx = rows.indexOf(row);
                if ((rules[idx].conditions || []).length <= 1) return;
                rules[idx].conditions.splice(condIdx, 1);
                render();
            } else if (removeRule) {
                collectFromDom();
                const card = removeRule.closest('.unlock-rule-card');
                const idx = Number(card.getAttribute('data-rule-index'));
                rules.splice(idx, 1);
                render();
            }
        });

        listEl.addEventListener('change', function(e) {
            if (!e.target.classList.contains('unlock-cond-metric')) return;
            const row = e.target.closest('.unlock-cond-row');
            const metric = e.target.value;
            const spec = metrics[metric] || {};
            row.querySelector('.unlock-cond-op').innerHTML = operatorOptions(metric, spec.default_op);
            const wrap = row.querySelector('.unlock-cond-value-wrap');
            wrap.innerHTML = valueControl(metric, spec.widget === 'boolean' ? true : (spec.widget === 'segment' ? 'health' : ''));
        });

        addBtn.addEventListener('click', function() {
            collectFromDom();
            rules.push(defaultRule());
            render();
        });

        formEl.addEventListener('submit', function() {
            jsonEl.value = JSON.stringify({ rules: collectFromDom() });
        });

        render();
    })();

    // Live GST Calculation Preview for Price Inputs
    function updateGstPreviews() {
        document.querySelectorAll('.price-calc-input').forEach(function(input) {
            const targetId = input.getAttribute('data-target');
            if (!targetId) return;
            const targetEl = document.getElementById(targetId);
            if (!targetEl) return;
            const val = parseFloat(input.value) || 0;
            const gst = val * 0.18;
            const total = Math.round(val + gst);
            targetEl.textContent = `+ 18% GST (₹${gst.toFixed(2)}) = ₹${total.toLocaleString('en-IN')} Total`;
        });
    }

    document.querySelectorAll('.price-calc-input').forEach(function(input) {
        input.addEventListener('input', function() {
            updateGstPreviews();
            if (input.id === 'starterScratchPrice' || input.id === 'starterPromoPrice' ||
                input.id === 'proScratchPrice' || input.id === 'proPromoPrice') {
                refreshAllTierPricesFromDiscounts();
            }
        });
    });
    ['starterScratchSwitch', 'profScratchSwitch'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', refreshAllTierPricesFromDiscounts);
        }
    });
    updateGstPreviews();
});
