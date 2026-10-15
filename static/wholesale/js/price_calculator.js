/**
 * Real-Time Quantity & Tier Price Calculator for Product Detail Page
 */

document.addEventListener('DOMContentLoaded', function () {
    const qtyInput = document.getElementById('calcQuantityInput');
    const unitPriceDisplay = document.getElementById('calcUnitPriceDisplay');
    const subtotalDisplay = document.getElementById('calcSubtotalDisplay');
    const taxDisplay = document.getElementById('calcTaxDisplay');
    const totalDisplay = document.getElementById('calcTotalDisplay');
    const savingsDisplay = document.getElementById('calcSavingsDisplay');
    const tierRows = document.querySelectorAll('.ws-tier-table tbody tr');

    if (!qtyInput) return;

    const productId = qtyInput.getAttribute('data-product-id');
    const minMoq = parseInt(qtyInput.getAttribute('min') || 1);

    function calculate() {
        let qty = parseInt(qtyInput.value || minMoq);
        if (qty < minMoq) {
            qty = minMoq;
            qtyInput.value = minMoq;
        }

        // Highlight matching tier row locally
        tierRows.forEach(row => {
            const minT = parseInt(row.getAttribute('data-min'));
            const maxT = row.getAttribute('data-max') ? parseInt(row.getAttribute('data-max')) : Infinity;
            row.classList.remove('ws-tier-highlight');
            if (qty >= minT && qty <= maxT) {
                row.classList.add('ws-tier-highlight');
            }
        });

        // Fetch accurate calculated breakdown from API
        fetch(`/wholesale/product/${productId}/calculate-price/?quantity=${qty}`)
            .then(res => res.json())
            .then(data => {
                if (unitPriceDisplay) unitPriceDisplay.textContent = `₹${data.unit_price.toFixed(2)}`;
                if (subtotalDisplay) subtotalDisplay.textContent = `₹${data.total_base.toFixed(2)}`;
                if (taxDisplay) {
                    if (data.tax_included) {
                        taxDisplay.textContent = `Included (${data.tax_percent}%)`;
                    } else {
                        taxDisplay.textContent = `+₹${data.tax_amount.toFixed(2)} (${data.tax_percent}%)`;
                    }
                }
                if (totalDisplay) totalDisplay.textContent = `₹${data.total_final.toFixed(2)}`;

                if (savingsDisplay) {
                    if (data.savings_vs_base > 0) {
                        savingsDisplay.style.display = 'block';
                        savingsDisplay.innerHTML = `<i class="fa-solid fa-tag me-1"></i> You save ₹${data.savings_vs_base.toFixed(2)} with volume discount!`;
                    } else {
                        savingsDisplay.style.display = 'none';
                    }
                }
            })
            .catch(err => console.error("Price calculation error:", err));
    }

    qtyInput.addEventListener('input', calculate);
    qtyInput.addEventListener('change', calculate);

    const btnMinus = document.getElementById('btnQtyMinus');
    const btnPlus = document.getElementById('btnQtyPlus');

    if (btnMinus) {
        btnMinus.addEventListener('click', function () {
            let val = parseInt(qtyInput.value || minMoq);
            if (val > minMoq) {
                qtyInput.value = val - 1;
                calculate();
            }
        });
    }

    if (btnPlus) {
        btnPlus.addEventListener('click', function () {
            let val = parseInt(qtyInput.value || minMoq);
            qtyInput.value = val + 1;
            calculate();
        });
    }

    // Run initial calculation
    calculate();
});
