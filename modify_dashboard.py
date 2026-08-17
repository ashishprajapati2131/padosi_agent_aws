import os

filepath = r'c:\Users\DELL\Downloads\7_22_2026\src\templates\agents\dashboard.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

append_code = '''
    // Handle SubscriptionPlan Feature Locks Dynamically for Dashboard
    const planPermissions = {
      recentLeads: {% if not agent_plan or agent_plan.show_recent_leads %}true{% else %}false{% endif %},
      salesInsights: {% if not agent_plan or agent_plan.show_sales_insights %}true{% else %}false{% endif %}
    };

    function lockSection($el) {
      if ($el.length === 0) return;
      $el.css({
          'position': 'relative',
          'pointer-events': 'none',
          'opacity': '0.75'
      });
      if ($el.find('.locked-plan-overlay').length === 0) {
        $el.append(`
          <div class="locked-plan-overlay" style="position:absolute; top:0; left:0; right:0; bottom:0; background:rgba(255,255,255,0.8); z-index:10; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:auto; text-align:center; border-radius: 12px;">
            <i class="fas fa-lock mb-2 text-muted" style="font-size: 24px;"></i>
            <h5 class="font-weight-bold text-dark">Feature Locked</h5>
            <p class="text-muted mb-0 small">Requires a plan upgrade to unlock.</p>
          </div>
        `);
      }
    }

    if (!planPermissions.recentLeads) {
      // Find the recent leads section (contains the table)
      lockSection($('.table-responsive').closest('.card'));
    }
    
    if (!planPermissions.salesInsights) {
      // Find the sales insights chart section
      lockSection($('#chart-container'));
    }
  });
</script>
'''

search_str = '    });\n</script>'
if search_str in content:
    content = content.replace(search_str, append_code)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Successfully modified dashboard.html')
else:
    print('Could not find target string')
