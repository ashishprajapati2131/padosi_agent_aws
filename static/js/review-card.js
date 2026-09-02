(function () {
    const advisor = window.PADOSI_ADVISOR || {
        name: 'Advisor',
        designation: 'Insurance Advisor',
        image: '',
        slug: ''
    };

    const reviewUrl = window.PADOSI_REVIEW_URL || (
        advisor.slug ? `https://padosiagent.com/review/${advisor.slug}` : ''
    );

    function $(id) {
        return document.getElementById(id);
    }

    function ReviewCard() {
        renderQRCodeSection();
        bindToolbar();
        bindCopyFallback();
    }

    function AdvisorProfile() {
        return advisor;
    }

    function renderQRCodeSection() {
        const mount = $('paReviewQr');
        if (!mount || !reviewUrl || typeof QRCode === 'undefined') return;
        mount.innerHTML = '';
        new QRCode(mount, {
            text: reviewUrl,
            width: 196,
            height: 196,
            colorDark: '#0b1f4d',
            colorLight: '#ffffff',
            correctLevel: QRCode.CorrectLevel.H
        });
        const img = mount.querySelector('img');
        if (img) {
            img.alt = `QR code to review ${advisor.name} on PadosiAgent`;
        }
    }

    function ReviewCTA() {
        return reviewUrl;
    }

    function toast(title) {
        if (window.Swal) {
            Swal.fire({ toast: true, position: 'top', timer: 2200, showConfirmButton: false, icon: 'success', title: title });
            return;
        }
        window.alert(title);
    }

    function copyReviewLink() {
        const text = reviewUrl;
        const done = function () { toast('Review link copied'); };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text).then(done).catch(function () {
                fallbackCopy(text); done();
            });
        }
        fallbackCopy(text);
        done();
    }

    function fallbackCopy(text) {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
    }

    function shareCard() {
        const payload = {
            title: `${advisor.name} | PadosiAgent`,
            text: `Please rate and review your experience with ${advisor.name} on PadosiAgent.`,
            url: reviewUrl
        };
        if (navigator.share) {
            navigator.share(payload).catch(function () {});
            return;
        }
        copyReviewLink();
    }

    function waitForImages(root) {
        const images = Array.from(root.querySelectorAll('img'));
        return Promise.all(images.map(function (img) {
            if (img.complete) return Promise.resolve();
            return new Promise(function (resolve) {
                img.addEventListener('load', resolve, { once: true });
                img.addEventListener('error', resolve, { once: true });
            });
        }));
    }

    async function downloadCard() {
        const card = document.getElementById('padosiReviewCard');
        if (!card || typeof html2canvas === 'undefined') {
            window.print();
            return;
        }
        const btn = $('paDownloadCard');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Preparing...';
        }
        try {
            await waitForImages(card);
            const canvas = await html2canvas(card, {
                scale: 2,
                useCORS: true,
                backgroundColor: '#ffffff',
                logging: false
            });
            const link = document.createElement('a');
            link.download = `PadosiAgent-review-card-${advisor.slug || 'advisor'}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
        } catch (err) {
            console.error(err);
            window.print();
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Download Card';
            }
        }
    }

    function bindToolbar() {
        const downloadBtn = $('paDownloadCard');
        const shareBtn = $('paShareCard');
        const copyBtn = $('paCopyReviewLink');
        if (downloadBtn) downloadBtn.addEventListener('click', downloadCard);
        if (shareBtn) shareBtn.addEventListener('click', shareCard);
        if (copyBtn) copyBtn.addEventListener('click', copyReviewLink);
    }

    function bindCopyFallback() {}

    window.PadosiReviewCard = {
        ReviewCard: ReviewCard,
        AdvisorProfile: AdvisorProfile,
        QRCodeSection: renderQRCodeSection,
        ReviewCTA: ReviewCTA,
        downloadCard: downloadCard,
        shareCard: shareCard,
        copyReviewLink: copyReviewLink
    };

    document.addEventListener('DOMContentLoaded', ReviewCard);
})();
