/**
 * Renders accordion filter UI and syncs YOUR PICKS / count badge.
 */
(function (global, $) {
  if (!$) return;

  var config = global.PA_FILTER_CONFIG;

  function esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/"/g, '&quot;');
  }

  function renderGroups(groups, ext) {
    return groups.map(function (group) {
      var cat = config.categories[group.key];
      if (!cat) return '';
      var sectionId = (cat.sectionId && ext.id === 'buy-new') ? ' id="' + cat.sectionId + '"' : '';
      var collapsed = '';
      var chips = group.items.map(function (item) {
        return (
          '<button type="button" class="circle-tile pa-filter-chip" ' +
          'data-product="' + esc(item.product) + '" ' +
          'data-ext-id="' + esc(ext.id) + '" ' +
          'data-pill-value="' + esc(ext.pillValue) + '">' +
          esc(item.label) +
          '</button>'
        );
      }).join('');
      return (
        '<div class="product-category-section pa-filter-cat' + collapsed + '" data-category="' + esc(cat.category) + '"' + sectionId + '>' +
        '<div class="pa-filter-cat-label">' + esc(cat.label) + '</div>' +
        '<div class="pa-filter-chip-grid">' + chips + '</div>' +
        '</div>'
      );
    }).join('');
  }

  function renderAccordions(mount) {
    if (!config || !mount) return;
    var html = config.externals.map(function (ext, idx) {
      var open = idx === 0 ? ' is-open' : '';
      return (
        '<div class="pa-filter-ext' + open + '" data-ext-id="' + esc(ext.id) + '" data-pill-value="' + esc(ext.pillValue) + '">' +
        '<button type="button" class="pa-filter-ext-head" aria-expanded="' + (idx === 0 ? 'true' : 'false') + '">' +
        '<span class="pa-filter-ext-icon"><i class="fas ' + esc(ext.icon) + '"></i></span>' +
        '<span class="pa-filter-ext-text">' +
        '<span class="pa-filter-ext-title">' + esc(ext.title) + '</span>' +
        (ext.subtitle ? '<span class="pa-filter-ext-sub">' + esc(ext.subtitle) + '</span>' : '') +
        '</span>' +
        '<span class="pa-filter-ext-chevron"><i class="fas fa-chevron-down"></i></span>' +
        '</button>' +
        '<div class="pa-filter-ext-body">' +
        renderGroups(ext.groups, ext) +
        (ext.footnote ? '<p class="pa-filter-footnote"><i class="fas fa-info-circle"></i> ' + esc(ext.footnote) + '</p>' : '') +
        (ext.id === 'buy-new' ? '<div id="life-insurance-disclaimer" class="pa-filter-disclaimer disclaimer-banner" style="display:none;"><i class="fas fa-info-circle"></i> Life insurance is not applicable for port/transfer</div>' : '') +
        '</div></div>'
      );
    }).join('');
    $(mount).html(html);
  }

  function activeExternalId() {
    var pill = $('.filter-pill.active').first().data('value');
    if (!pill) return 'buy-new';
    var found = null;
    config.externals.forEach(function (ext) {
      if (ext.pillValue === pill) found = ext.id;
    });
    if (found) return found;
    if (pill === 'Port / transfer') return 'renew-transfer';
    if (pill === 'Insurance audit') return 'check-policy';
    return 'buy-new';
  }

  function activateServicePill(pillValue) {
    var $pill = $('.filter-pill[data-value="' + pillValue + '"]');
    if (!$pill.length) return;
    if ($pill.hasClass('active')) return;
    $('.filter-pill').removeClass('active');
    $pill.addClass('active');
    if (typeof window.paFilterUpdateUiState === 'function') {
      window.paFilterUpdateUiState();
    }
  }

  function updatePicksAndCount() {
    var $wrap = $('#pa-filter-your-picks');
    var $chips = $('#pa-filter-picks-chips');
    var $count = $('#pa-filter-count-badge');
    var active = $('.circle-tile.active');
    var n = active.length;
    $count.text(n);
    $count.toggle(n > 0);
    if (n === 0) {
      $wrap.attr('hidden', 'hidden');
      $chips.empty();
      return;
    }
    $wrap.removeAttr('hidden');
    var html = '';
    active.each(function () {
      var $t = $(this);
      var label = $t.text().trim();
      var product = $t.data('product');
      var extId = $t.data('ext-id') || '';
      html += (
        '<button type="button" class="pa-filter-pick-chip" data-product="' + esc(product) + '" data-ext-id="' + esc(extId) + '">' +
        esc(label) + ' <span class="pa-filter-pick-x" aria-hidden="true">&times;</span></button>'
      );
    });
    $chips.html(html);
  }

  function bindEvents(mount) {
    $(mount).on('click', '.pa-filter-ext-head', function (e) {
      e.preventDefault();
      var $ext = $(this).closest('.pa-filter-ext');
      var isOpen = $ext.hasClass('is-open');
      $('.pa-filter-ext').removeClass('is-open').find('.pa-filter-ext-head').attr('aria-expanded', 'false');
      if (!isOpen) {
        $ext.addClass('is-open');
        $(this).attr('aria-expanded', 'true');
      }
    });

    $(document).on('click', '.circle-tile.pa-filter-chip', function (e) {
      var pillValue = $(this).data('pill-value');
      if (pillValue) {
        activateServicePill(pillValue);
      }
    });

    $(document).on('click', '.pa-filter-pick-chip', function (e) {
      e.preventDefault();
      var product = $(this).data('product');
      $('.circle-tile.active[data-product="' + product + '"]').removeClass('active');
      if (typeof window.paFilterSyncHidden === 'function') window.paFilterSyncHidden();
      updatePicksAndCount();
    });

    $(document).on('click', '#pa-filter-clear-link', function (e) {
      e.preventDefault();
      $('#clear-filters-btn').trigger('click');
    });

    $(document).on('click', '.pa-filter-close-btn', function (e) {
      e.preventDefault();
      if (window.innerWidth <= 1180 && typeof window.closeMobileFilter === 'function') {
        window.closeMobileFilter();
      } else {
        $('#sidebar-filters').hide();
        $('#agent-list-container').removeClass('col-lg-8 col-xl-9').addClass('col-lg-12');
        $('#toggle-compact-filter').removeClass('active');
      }
    });

    $(document).on('click', '.circle-tile', function () {
      setTimeout(updatePicksAndCount, 0);
    });
  }

  global.PAFilterUI = {
    render: function (selector) {
      var mount = document.querySelector(selector);
      if (!mount) return;
      renderAccordions(mount);
      bindEvents(mount);
      updatePicksAndCount();
    },
    updatePicksAndCount: updatePicksAndCount,
    activateServicePill: activateServicePill,
    activeExternalId: activeExternalId,
    expandForPill: function (pillValue) {
      var extId = null;
      config.externals.forEach(function (ext) {
        if (ext.pillValue === pillValue) extId = ext.id;
      });
      if (!extId) return;
      $('.pa-filter-ext').removeClass('is-open');
      $('.pa-filter-ext[data-ext-id="' + extId + '"]').addClass('is-open')
        .find('.pa-filter-ext-head').attr('aria-expanded', 'true');
    }
  };
})(window, window.jQuery);
