
(function () {
    var master = document.getElementById('growthEnabled');
    var fieldsWrap = document.getElementById('reviewGrowthFields');
    var starterUnlockMaster = document.getElementById('growthStarterUnlock');
    var starterUnlockFields = document.getElementById('starterUnlockFields');
    var upgradePriceMaster = document.getElementById('growthUpgradePrice');
    var upgradePriceFields = document.getElementById('reviewUpgradePriceFields');
    var badge = document.getElementById('reviewGrowthStatusBadge');
    if (!master || !fieldsWrap) return;

    function syncUpgradePriceUi() {
        if (!upgradePriceMaster || !upgradePriceFields) return;
        var priceOn = master.checked && upgradePriceMaster.checked;
        upgradePriceFields.style.opacity = priceOn ? '1' : '0.45';
        upgradePriceFields.querySelectorAll('input').forEach(function (el) {
            el.disabled = !priceOn;
        });
    }

    function syncStarterUnlockUi() {
        if (!starterUnlockMaster || !starterUnlockFields) return;
        var unlockOn = master.checked && starterUnlockMaster.checked;
        starterUnlockFields.style.opacity = unlockOn ? '1' : '0.45';
        starterUnlockFields.querySelectorAll('.starter-unlock-toggle').forEach(function (el) {
            el.disabled = !unlockOn;
        });
    }

    function syncReviewGrowthUi() {
        var on = master.checked;
        fieldsWrap.style.opacity = on ? '1' : '0.45';
        fieldsWrap.querySelectorAll('.growth-field, .growth-sub-toggle').forEach(function (el) {
            el.disabled = !on;
        });
        if (badge) {
            badge.textContent = on ? 'On' : 'Off';
            badge.classList.toggle('bg-success', on);
            badge.classList.toggle('bg-secondary', !on);
        }
        syncStarterUnlockUi();
        syncUpgradePriceUi();
    }

    master.addEventListener('change', syncReviewGrowthUi);
    if (starterUnlockMaster) {
        starterUnlockMaster.addEventListener('change', syncStarterUnlockUi);
    }
    if (upgradePriceMaster) {
        upgradePriceMaster.addEventListener('change', syncUpgradePriceUi);
    }
    syncReviewGrowthUi();

    var form = document.getElementById('reviewGrowthForm');
    if (form) {
        form.addEventListener('submit', function () {
            fieldsWrap.querySelectorAll('.growth-field, .growth-sub-toggle').forEach(function (el) {
                el.disabled = false;
            });
            if (starterUnlockFields) {
                starterUnlockFields.querySelectorAll('.starter-unlock-toggle').forEach(function (el) {
                    el.disabled = false;
                });
            }
        });
    }
})();
