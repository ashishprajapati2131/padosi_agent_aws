import os

filepath = r'c:\Users\DELL\Downloads\7_22_2026\src\templates\agents\edit_profile.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

append_code = '''    }

    // Handle SubscriptionPlan Feature Locks Dynamically
    const planPermissions = {
      profile: {% if not agent_plan or agent_plan.show_profile_section %}true{% else %}false{% endif %},
      agentCertificate: {% if not agent_plan or agent_plan.show_agent_certificate %}true{% else %}false{% endif %},
      careerTimeline: {% if not agent_plan or agent_plan.show_career_timeline %}true{% else %}false{% endif %},
      professionalBio: {% if not agent_plan or agent_plan.show_professional_bio %}true{% else %}false{% endif %},
      portfolio: {% if not agent_plan or agent_plan.show_portfolio %}true{% else %}false{% endif %},
      claimSupport: {% if not agent_plan or agent_plan.show_claim_support %}true{% else %}false{% endif %}
    };

    function lockSection($el) {
      if ($el.length === 0) return;
      $el.addClass('locked-plan-section').css({
          'position': 'relative',
          'pointer-events': 'none',
          'opacity': '0.75'
      });
      // add overlay
      if ($el.find('.locked-plan-overlay').length === 0) {
        $el.append(`
          <div class="locked-plan-overlay" style="position:absolute; top:0; left:0; right:0; bottom:0; background:rgba(255,255,255,0.8); z-index:10; display:flex; flex-direction:column; align-items:center; justify-content:center; pointer-events:auto; text-align:center;">
            <i class="fas fa-lock mb-2 text-muted" style="font-size: 24px;"></i>
            <h5 class="font-weight-bold text-dark">Feature Locked</h5>
            <p class="text-muted mb-0 small">Requires a plan upgrade to unlock.</p>
          </div>
        `);
      }
    }

    if (!planPermissions.profile) lockSection($('#step-1'));
    if (!planPermissions.agentCertificate) lockSection($('#step-2'));
    if (!planPermissions.portfolio) lockSection($('#step-3'));
    if (!planPermissions.careerTimeline) lockSection($('#step-4'));
    if (!planPermissions.professionalBio) {
      // Step 5 has bio
      lockSection($('#step-5 .card').first());
    }

</script>'''

search_str = '    }\n\n\n</script>'
if search_str in content:
    content = content.replace(search_str, append_code)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Successfully modified edit_profile.html')
else:
    print('Could not find target string')
