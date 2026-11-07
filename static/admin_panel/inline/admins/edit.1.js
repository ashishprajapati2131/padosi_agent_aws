
    document.addEventListener('DOMContentLoaded', function() {
        const roleSelect = document.getElementById('roleSelect');
        const permissionsWrapper = document.getElementById('permissionsWrapper');

        if (roleSelect) {
            function handleRoleChange() {
                if (roleSelect.value === 'super') {
                    permissionsWrapper.style.display = 'none';
                } else {
                    permissionsWrapper.style.display = 'block';
                }
            }

            roleSelect.addEventListener('change', handleRoleChange);
            handleRoleChange(); // Initial run
            
            // Auto-check Pending Approvals parent if both children are checked, 
            // and sync their states when clicked.
            const permApprovals = document.getElementById('perm_approvals');
            const permVerification = document.getElementById('perm_approvals_awaiting_verification');
            const permLicenses = document.getElementById('perm_approvals_missing_licenses');
            
            if (permApprovals && permVerification && permLicenses) {
                permApprovals.checked = permVerification.checked || permLicenses.checked;
                
                permApprovals.addEventListener('change', (e) => {
                    permVerification.checked = e.target.checked;
                    permLicenses.checked = e.target.checked;
                });
                
                const syncParent = () => {
                    permApprovals.checked = permVerification.checked || permLicenses.checked;
                };
                permVerification.addEventListener('change', syncParent);
                permLicenses.addEventListener('change', syncParent);
            }
        }
    });

    function toggleAllCheckboxes(checked) {
        document.querySelectorAll('.permission-checkbox').forEach(cb => {
            cb.checked = checked;
        });
    }
