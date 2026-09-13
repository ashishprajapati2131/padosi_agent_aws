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

    function fitCardToScreen() {
        const stage = document.querySelector('.pa-rc-stage');
        const card = document.getElementById('padosiReviewCard');
        if (!stage || !card) return;

        if (card.getAttribute('data-capturing') === 'true') return;

        card.style.transform = '';
        card.style.transformOrigin = '';
        stage.style.height = '';

        const page = document.querySelector('.pa-rc-page');
        let padding = 28;
        if (page) {
            const cs = getComputedStyle(page);
            padding = (parseFloat(cs.paddingLeft) || 14) + (parseFloat(cs.paddingRight) || 14);
        }
        
        const availableWidth = Math.min(window.innerWidth - padding, stage.parentElement ? stage.parentElement.clientWidth - padding : window.innerWidth - padding);
        const cardWidth = 780;

        if (availableWidth < cardWidth && availableWidth > 0) {
            const scale = availableWidth / cardWidth;
            card.style.transform = `scale(${scale})`;
            card.style.transformOrigin = 'top center';
            const unscaledHeight = card.offsetHeight;
            stage.style.height = `${unscaledHeight * scale}px`;
        }
    }

    function ReviewCard() {
        renderQRCodeSection();
        bindToolbar();
        bindCopyFallback();
        fitCardToScreen();
        window.addEventListener('resize', fitCardToScreen);
        window.addEventListener('orientationchange', fitCardToScreen);
        setTimeout(fitCardToScreen, 200);
        setTimeout(fitCardToScreen, 800);
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
        setTimeout(fitCardToScreen, 100);
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

    async function downloadPDF() {
        const card = document.getElementById('padosiReviewCard');
        const stage = document.querySelector('.pa-rc-stage');
        if (!card || typeof html2canvas === 'undefined') {
            window.print();
            return;
        }
        const btn = $('paDownloadPdf');
        const origText = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Preparing PDF...';
        }
        try {
            card.setAttribute('data-capturing', 'true');
            card.style.transform = 'none';
            card.style.transformOrigin = 'initial';
            if (stage) stage.style.height = 'auto';

            await waitForImages(card);
            const canvas = await html2canvas(card, {
                scale: 2,
                useCORS: true,
                backgroundColor: '#ffffff',
                logging: false
            });
            const imgData = canvas.toDataURL('image/jpeg', 0.98);
            const cardWidth = canvas.width / 2;
            const cardHeight = canvas.height / 2;
            
            const { jsPDF } = window.jspdf || {};
            if (jsPDF) {
                const pdf = new jsPDF({
                    orientation: cardWidth > cardHeight ? 'landscape' : 'portrait',
                    unit: 'px',
                    format: [cardWidth, cardHeight]
                });
                pdf.addImage(imgData, 'JPEG', 0, 0, cardWidth, cardHeight);
                pdf.save(`PadosiAgent-review-card-${advisor.slug || 'advisor'}.pdf`);
            } else {
                window.print();
            }
        } catch (err) {
            console.error('PDF Download Error:', err);
            window.print();
        } finally {
            card.removeAttribute('data-capturing');
            fitCardToScreen();
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origText || '<i class="fa-solid fa-file-pdf mr-1"></i> Download PDF';
            }
        }
    }

    async function downloadCard() {
        const card = document.getElementById('padosiReviewCard');
        const stage = document.querySelector('.pa-rc-stage');
        if (!card || typeof html2canvas === 'undefined') {
            window.print();
            return;
        }
        const btn = $('paDownloadCard');
        const origText = btn ? btn.innerHTML : '';
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Preparing PNG...';
        }
        try {
            card.setAttribute('data-capturing', 'true');
            card.style.transform = 'none';
            card.style.transformOrigin = 'initial';
            if (stage) stage.style.height = 'auto';

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
            card.removeAttribute('data-capturing');
            fitCardToScreen();
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origText || '<i class="fa-solid fa-file-image mr-1"></i> Download PNG';
            }
        }
    }

    function bindToolbar() {
        const downloadPdfBtn = $('paDownloadPdf');
        const downloadBtn = $('paDownloadCard');
        const shareBtn = $('paShareCard');
        const copyBtn = $('paCopyReviewLink');
        if (downloadPdfBtn) downloadPdfBtn.addEventListener('click', downloadPDF);
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
        downloadPDF: downloadPDF,
        downloadCard: downloadCard,
        shareCard: shareCard,
        copyReviewLink: copyReviewLink,
        fitCardToScreen: fitCardToScreen
    };

    document.addEventListener('DOMContentLoaded', ReviewCard);
})();
