/**
 * Product Wizard JavaScript Handler
 * Manages 8-step wizard navigation, dynamic price tiers builder, variants matrix, and live preview.
 */

document.addEventListener('DOMContentLoaded', function () {
    let currentStep = 1;
    const totalSteps = 8;

    const stepSections = document.querySelectorAll('.ws-wizard-section');
    const stepIndicators = document.querySelectorAll('.ws-wizard-step');
    const btnPrev = document.getElementById('btnWizardPrev');
    const btnNext = document.getElementById('btnWizardNext');
    const btnSaveDraft = document.getElementById('btnWizardSaveDraft');
    const btnSubmitApproval = document.getElementById('btnWizardSubmit');

    function showStep(step) {
        stepSections.forEach(sec => sec.style.display = 'none');
        const target = document.getElementById(`wizardStep${step}`);
        if (target) target.style.display = 'block';

        stepIndicators.forEach((ind, idx) => {
            ind.classList.remove('active', 'completed');
            if (idx + 1 === step) ind.classList.add('active');
            else if (idx + 1 < step) ind.classList.add('completed');
        });

        // Toggle buttons
        if (btnPrev) btnPrev.style.display = step > 1 ? 'inline-block' : 'none';
        if (btnNext) btnNext.style.display = step < totalSteps ? 'inline-block' : 'none';
        if (btnSubmitApproval) btnSubmitApproval.style.display = step === totalSteps ? 'inline-block' : 'none';

        if (step === totalSteps) {
            updateLivePreview();
        }

        window.scrollTo({ top: 120, behavior: 'smooth' });
    }

    if (btnNext) {
        btnNext.addEventListener('click', function () {
            if (validateCurrentStep(currentStep)) {
                if (currentStep < totalSteps) {
                    currentStep++;
                    showStep(currentStep);
                }
            }
        });
    }

    if (btnPrev) {
        btnPrev.addEventListener('click', function () {
            if (currentStep > 1) {
                currentStep--;
                showStep(currentStep);
            }
        });
    }

    stepIndicators.forEach((ind, idx) => {
        ind.addEventListener('click', function () {
            const targetStep = idx + 1;
            if (targetStep < currentStep || validateCurrentStep(currentStep)) {
                currentStep = targetStep;
                showStep(currentStep);
            }
        });
    });

    function validateCurrentStep(step) {
        if (step === 1) {
            const title = document.getElementById('id_title').value.trim();
            const category = document.getElementById('id_category').value;
            const sku = document.getElementById('id_sku').value.trim();
            if (!title) {
                alert('Please enter a Product Title.');
                document.getElementById('id_title').focus();
                return false;
            }
            if (!category) {
                alert('Please select a Category.');
                document.getElementById('id_category').focus();
                return false;
            }
            if (!sku) {
                alert('Please enter a SKU or Product Code.');
                document.getElementById('id_sku').focus();
                return false;
            }
        } else if (step === 3) {
            const basePrice = parseFloat(document.getElementById('id_base_price').value || 0);
            const moq = parseInt(document.getElementById('id_moq').value || 0);
            if (basePrice <= 0) {
                alert('Please enter a valid Base Wholesale Price (> 0).');
                document.getElementById('id_base_price').focus();
                return false;
            }
            if (moq < 1) {
                alert('Minimum Order Quantity must be at least 1.');
                document.getElementById('id_moq').focus();
                return false;
            }
        }
        return true;
    }

    // ── Dynamic Price Tier Builder ───────────────────────────────────────────
    const tierTableBody = document.getElementById('tierTableBody');
    const btnAddTier = document.getElementById('btnAddTier');

    window.addTierRow = function (minQty = '', maxQty = '', price = '') {
        if (!tierTableBody) return;
        const row = document.createElement('tr');
        row.className = 'tier-row';
        row.innerHTML = `
            <td><input type="number" class="form-control tier-min-qty" min="1" value="${minQty}" placeholder="e.g. 10"></td>
            <td><input type="number" class="form-control tier-max-qty" min="1" value="${maxQty}" placeholder="Leave blank for +"></td>
            <td><div class="input-group"><span class="input-group-text">₹</span><input type="number" step="0.01" class="form-control tier-price" value="${price}" placeholder="0.00"></div></td>
            <td class="text-center"><button type="button" class="btn btn-sm btn-outline-danger btn-remove-tier"><i class="fa-solid fa-trash"></i></button></td>
        `;
        tierTableBody.appendChild(row);

        row.querySelector('.btn-remove-tier').addEventListener('click', function () {
            row.remove();
        });
    };

    if (btnAddTier) {
        btnAddTier.addEventListener('click', function () {
            addTierRow();
        });
    }

    // Load existing tiers from JSON injected into window
    if (window.EXISTING_TIERS && Array.isArray(window.EXISTING_TIERS)) {
        window.EXISTING_TIERS.forEach(t => addTierRow(t.min_qty, t.max_qty, t.price));
    }

    // ── Dynamic Variant Builder ──────────────────────────────────────────────
    const variantTableBody = document.getElementById('variantTableBody');
    const btnAddVariant = document.getElementById('btnAddVariant');

    window.addVariantRow = function (title = '', sku = '', price = '', stock = '') {
        if (!variantTableBody) return;
        const row = document.createElement('tr');
        row.className = 'variant-row';
        row.innerHTML = `
            <td><input type="text" class="form-control var-title" value="${title}" placeholder="e.g. Size: XL | Navy Blue"></td>
            <td><input type="text" class="form-control var-sku" value="${sku}" placeholder="Optional SKU"></td>
            <td><input type="number" step="0.01" class="form-control var-price" value="${price}" placeholder="Override ₹"></td>
            <td><input type="number" class="form-control var-stock" value="${stock}" min="0" placeholder="0"></td>
            <td class="text-center"><button type="button" class="btn btn-sm btn-outline-danger btn-remove-variant"><i class="fa-solid fa-trash"></i></button></td>
        `;
        variantTableBody.appendChild(row);

        row.querySelector('.btn-remove-variant').addEventListener('click', function () {
            row.remove();
        });
    };

    if (btnAddVariant) {
        btnAddVariant.addEventListener('click', function () {
            addVariantRow();
        });
    }

    if (window.EXISTING_VARIANTS && Array.isArray(window.EXISTING_VARIANTS)) {
        window.EXISTING_VARIANTS.forEach(v => addVariantRow(v.title, v.sku, v.price, v.stock));
    }

    // ── Form Submit Serialization ────────────────────────────────────────────
    const wizardForm = document.getElementById('productWizardForm');
    if (wizardForm) {
        wizardForm.addEventListener('submit', function () {
            // Serialize Tiers
            const tiers = [];
            document.querySelectorAll('#tierTableBody .tier-row').forEach(row => {
                const minVal = row.querySelector('.tier-min-qty').value;
                const maxVal = row.querySelector('.tier-max-qty').value;
                const priceVal = row.querySelector('.tier-price').value;
                if (minVal && priceVal) {
                    tiers.push({
                        min_qty: parseInt(minVal),
                        max_qty: maxVal ? parseInt(maxVal) : null,
                        price: parseFloat(priceVal)
                    });
                }
            });
            document.getElementById('id_price_tiers_json').value = JSON.stringify(tiers);

            // Serialize Variants
            const variants = [];
            document.querySelectorAll('#variantTableBody .variant-row').forEach(row => {
                const title = row.querySelector('.var-title').value.trim();
                const sku = row.querySelector('.var-sku').value.trim();
                const price = row.querySelector('.var-price').value;
                const stock = row.querySelector('.var-stock').value;
                if (title) {
                    variants.push({
                        title: title,
                        sku: sku || null,
                        price: price ? parseFloat(price) : null,
                        stock: stock ? parseInt(stock) : 0
                    });
                }
            });
            document.getElementById('id_variants_json').value = JSON.stringify(variants);
        });
    }

    // ── Step 8 Live Preview Generator ────────────────────────────────────────
    function updateLivePreview() {
        const previewTitle = document.getElementById('previewTitle');
        const previewSku = document.getElementById('previewSku');
        const previewPrice = document.getElementById('previewPrice');
        const previewMoq = document.getElementById('previewMoq');
        const previewStock = document.getElementById('previewStock');
        const previewLocation = document.getElementById('previewLocation');
        const previewDesc = document.getElementById('previewDesc');

        if (previewTitle) previewTitle.textContent = document.getElementById('id_title').value || 'Product Title';
        if (previewSku) previewSku.textContent = document.getElementById('id_sku').value || 'SKU-001';
        if (previewPrice) previewPrice.textContent = '₹' + (document.getElementById('id_base_price').value || '0.00');
        if (previewMoq) previewMoq.textContent = (document.getElementById('id_moq').value || '1') + ' ' + (document.getElementById('id_unit_of_measure').value || 'Units');
        if (previewStock) previewStock.textContent = (document.getElementById('id_stock_quantity').value || '0') + ' Units Available';
        if (previewLocation) previewLocation.textContent = document.getElementById('id_dispatch_location').value || 'Dispatch: Pan India';
        if (previewDesc) previewDesc.textContent = document.getElementById('id_short_description').value || document.getElementById('id_description').value || '';
    }

    // Initialize first step
    showStep(currentStep);
});
