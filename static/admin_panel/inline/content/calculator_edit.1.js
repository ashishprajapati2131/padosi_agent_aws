
document.getElementById('add-faq').addEventListener('click', function () {
    const tpl = document.getElementById('faq-template');
    document.getElementById('faq-list').appendChild(tpl.content.cloneNode(true));
});
