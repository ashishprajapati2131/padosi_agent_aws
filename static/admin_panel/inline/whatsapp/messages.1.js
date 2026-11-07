
    function addKeywordRow() {
        const row = document.getElementById('keywordRowTemplate').content.cloneNode(true);
        document.getElementById('keywordRows').appendChild(row);
    }
    function removeKeywordRow(btn) {
        btn.closest('.keyword-row').remove();
    }
