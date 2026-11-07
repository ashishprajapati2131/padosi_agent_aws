
function previewSelectedBanner(input) {
    if (input.files && input.files[0]) {
        var reader = new FileReader();
        reader.onload = function(e) {
            document.getElementById('imagePreview').src = e.target.result;
            document.getElementById('imagePreviewContainer').classList.remove('d-none');
        }
        reader.readAsDataURL(input.files[0]);
    }
}

function clearSelectedBanner() {
    var input = document.getElementById('bannerImageInput');
    input.value = '';
    document.getElementById('imagePreview').src = '';
    document.getElementById('imagePreviewContainer').classList.add('d-none');
}
