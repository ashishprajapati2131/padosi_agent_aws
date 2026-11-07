
    function viewLogPayload(id) {
        const data = $('#payload-' + id).val();
        $('#logDataViewer').text(data);
        const modal = new bootstrap.Modal(document.getElementById('logModal'));
        modal.show();
    }
