
  function switchFtTab(btn, paneId) {
    document.querySelectorAll('#ftTabs button').forEach(function(b){ b.classList.remove('active'); });
    document.querySelectorAll('#ftTabContent > div').forEach(function(p){ p.style.display='none'; });
    btn.classList.add('active');
    var p = document.getElementById(paneId);
    if (p) p.style.display = 'block';
  }
  