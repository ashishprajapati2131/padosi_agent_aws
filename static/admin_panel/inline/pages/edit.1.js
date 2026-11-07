
// Auto-generate slug from title (only if slug is empty or unchanged)
var titleInput = document.getElementById('pageTitle');
var slugInput  = document.getElementById('pageSlug');
var userEditedSlug = slugInput.value.length > 0;

titleInput.addEventListener('input', function() {
    if (!userEditedSlug) {
        slugInput.value = this.value
            .toLowerCase()
            .trim()
            .replace(/[^a-z0-9\s-]/g, '')
            .replace(/\s+/g, '-')
            .replace(/-+/g, '-');
    }
});
slugInput.addEventListener('input', function() {
    userEditedSlug = this.value.length > 0;
});

// Character counters
var contentArea = document.getElementById('pageContent');
var contentCount = document.getElementById('contentCharCount');
function updateContentCount() {
    contentCount.textContent = contentArea.value.length.toLocaleString() + ' chars';
}
contentArea.addEventListener('input', updateContentCount);
updateContentCount();

var metaDesc  = document.getElementById('metaDesc');
var metaCount = document.getElementById('metaDescCount');
function updateMetaCount() {
    var len = metaDesc.value.length;
    metaCount.textContent = len + ' / 160 chars';
    metaCount.style.color = len > 160 ? '#ef4444' : 'var(--text-muted)';
}
metaDesc.addEventListener('input', updateMetaCount);
updateMetaCount();

// Raw HTML hint toggle and CKEditor
var rawCodeToggle = document.getElementById('isRawCode');
var rawCodeHint   = document.getElementById('rawCodeHint');
var contentArea   = document.getElementById('pageContent');
var guideBox      = document.getElementById('ai-guide-box');
var previewBtn    = document.getElementById('preview-code-btn');
let myEditor = null;

function initCKEditor() {
    if (myEditor) return Promise.resolve(myEditor);
    
    return ClassicEditor
        .create(document.querySelector('#pageContent'), {
            toolbar: {
                items: [
                    'heading', '|',
                    'bold', 'italic', 'underline', 'strikethrough', '|',
                    'link', 'blockQuote', 'insertTable', '|',
                    'bulletedList', 'numberedList', '|',
                    'outdent', 'indent', '|',
                    'undo', 'redo'
                ]
            }
        })
        .then(editor => {
            myEditor = editor;
            return editor;
        })
        .catch(error => console.error(error));
}

function destroyCKEditor() {
    if (!myEditor) return Promise.resolve();
    return myEditor.destroy().then(() => { myEditor = null; });
}

function toggleEditorMode(isRaw) {
    if (isRaw) {
        destroyCKEditor().then(() => {
            contentArea.style.setProperty('display', 'block', 'important');
            contentArea.classList.add('raw-code-editor');
            if (guideBox) guideBox.classList.remove('d-none');
            if (previewBtn) previewBtn.classList.remove('d-none');
            if (rawCodeHint) rawCodeHint.style.display = '';
        });
    } else {
        contentArea.style.setProperty('display', 'none', 'important');
        contentArea.classList.remove('raw-code-editor');
        if (guideBox) guideBox.classList.add('d-none');
        if (previewBtn) previewBtn.classList.add('d-none');
        if (rawCodeHint) rawCodeHint.style.display = 'none';
        initCKEditor();
    }
}

// Initial setup
toggleEditorMode(rawCodeToggle.checked);

rawCodeToggle.addEventListener('change', function() {
    toggleEditorMode(this.checked);
});

// Live Preview
if (previewBtn) {
    previewBtn.addEventListener('click', function() {
        const code = document.getElementById('pageContent').value;
        const iframe = document.getElementById('preview-iframe');
        // Opaque-origin sandbox (no allow-same-origin): the previewed page's
        // scripts still run, but cannot reach the admin panel or its session.
        iframe.srcdoc = code;
        const modal = new bootstrap.Modal(document.getElementById('previewModal'));
        modal.show();
    });
}
