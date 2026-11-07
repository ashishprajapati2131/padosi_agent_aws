
function setBannerTheme(themeKey, bgStyle, textStyle) {
    document.getElementById('bannerBgColor').value = bgStyle;
    document.getElementById('bannerTextColor').value = textStyle;
    syncSimulator();
}

function syncSimulator() {
    // 1. Sync Announcement Bar
    var msg = document.getElementById('bannerMessageInput').value.trim();
    var btnText = document.getElementById('bannerBtnTextInput').value.trim();
    var bgColor = document.getElementById('bannerBgColor').value;
    var textColor = document.getElementById('bannerTextColor').value;
    var isDismissible = document.getElementById('bannerDismissible').checked;
    var isBannerActive = document.getElementById('bannerActiveSwitch').checked;

    var bar = document.getElementById('simAnnouncementBar');
    var barText = document.getElementById('simBannerText');
    var barBtn = document.getElementById('simBannerBtn');
    var barClose = document.getElementById('simBannerClose');

    if (isBannerActive) {
        bar.style.display = 'flex';
        bar.style.background = bgColor;
        bar.style.color = textColor;
        barText.textContent = msg || 'Special Announcement Banner';
        if (btnText) {
            barBtn.textContent = btnText + ' →';
            barBtn.style.display = 'inline-block';
        } else {
            barBtn.style.display = 'none';
        }
        barClose.style.display = isDismissible ? 'inline-block' : 'none';
    } else {
        bar.style.display = 'none';
    }

    // 2. Sync Exit Popup
    var eyebrow = document.getElementById('popupEyebrowInput').value.trim();
    var title = document.getElementById('popupTitleInput').value.trim();
    var desc = document.getElementById('popupDescInput').value.trim();
    var pBtnText = document.getElementById('popupBtnTextInput').value.trim();

    document.getElementById('simPopupEyebrow').textContent = eyebrow || 'SPECIAL OFFER';
    document.getElementById('simPopupTitle').textContent = title || 'Need Help?';
    document.getElementById('simPopupDesc').textContent = desc || 'Connect with verified advisors.';
    document.getElementById('simPopupBtn').textContent = pBtnText || 'Connect Now';
}

function toggleSimPopup() {
    var modal = document.getElementById('simPopupModal');
    if (modal.classList.contains('d-none')) {
        modal.classList.remove('d-none');
    } else {
        modal.classList.add('d-none');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    syncSimulator();
});
