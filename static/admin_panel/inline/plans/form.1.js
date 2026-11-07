
$(document).ready(function() {
    let showingPreview = false;
    const btn = $('#toggleHtmlBtn');
    const editor = $('#htmlEditorWrapper');
    const preview = $('#htmlPreviewWrapper');
    const input = $('#htmlCodeInput');
    const actualPriceInput = $('input[name="actual_price"]');
    const discountedPriceInput = $('input[name="discounted_price"]');
    
    function updatePreviewContent() {
        let htmlContent = input.val();
        const actualPrice = actualPriceInput.val() || '0.00';
        const discountedPrice = discountedPriceInput.val() || '0.00';
        
        // Replace placeholders globally
        htmlContent = htmlContent.replace(/\{\{\s*actual_price\s*\}\}/g, actualPrice);
        htmlContent = htmlContent.replace(/\{\{\s*discounted_price\s*\}\}/g, discountedPrice);
        
        preview.html(htmlContent);
    }
    
    btn.on('click', function() {
        showingPreview = !showingPreview;
        
        if (showingPreview) {
            updatePreviewContent();
            
            // Switch UI
            editor.addClass('d-none');
            preview.removeClass('d-none');
            btn.html('<i class="fa-solid fa-code me-1"></i> Edit HTML Code');
            btn.removeClass('btn-outline-primary').addClass('btn-primary');
        } else {
            // Switch UI
            preview.addClass('d-none');
            editor.removeClass('d-none');
            btn.html('<i class="fa-solid fa-eye me-1"></i> View Live Preview');
            btn.removeClass('btn-primary').addClass('btn-outline-primary');
        }
    });
    
    // Update preview live when prices change
    actualPriceInput.on('input', function() {
        if (showingPreview) updatePreviewContent();
    });
    
    discountedPriceInput.on('input', function() {
        if (showingPreview) updatePreviewContent();
    });

    // Edit Profile Dependency Logic
    const $editProfileFull = $('input[name="show_edit_profile_full"]');
    const editProfileChildren = [
        'input[name="show_edit_profile_basic"]',
        'input[name="show_edit_profile_professional"]',
        'input[name="show_edit_profile_portfolio"]',
        'input[name="show_edit_profile_additional"]'
    ];
    
    function toggleEditProfileChildren() {
        const isChecked = $editProfileFull.is(':checked');
        editProfileChildren.forEach(selector => {
            const $child = $(selector);
            $child.prop('disabled', !isChecked);
            if (!isChecked) {
                // Optional: visually fade them or their containers
                $child.closest('tr').css('opacity', '0.6');
            } else {
                $child.closest('tr').css('opacity', '1');
            }
        });
    }

    if ($editProfileFull.length > 0) {
        $editProfileFull.on('change', toggleEditProfileChildren);
        toggleEditProfileChildren(); // Run on load
    }
});
