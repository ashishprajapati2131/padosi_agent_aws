import os
import re

tpl_dir = r"c:\Users\DELL\Downloads\7_22_2026\src\apps\insurance\templates\insurance"

replacements = {
    "insurance:agents.index": "insurance:agents_index",
    "insurance:agents.create": "insurance:agents_create",
    "insurance:agents.store": "insurance:agents_store",
    "insurance:agents.show": "insurance:agents_show",
    "insurance:agents.request_status": "insurance:request_status_change",
    
    "insurance:agents.cart.add": "insurance:add_to_cart",
    "insurance:agents.cart.remove": "insurance:remove_from_cart",
    "insurance:agents.cart.clear": "insurance:clear_cart",
    "insurance:agents.cart.checkout": "insurance:checkout_cart",
    
    "insurance:subusers.index": "insurance:subusers_index",
    "insurance:subusers.store": "insurance:subusers_store",
    "insurance:subusers.reset-password": "insurance:subusers_reset_password",
    "insurance:subusers.toggle-status": "insurance:subusers_toggle_status",
    
    "insurance:approvals.index": "insurance:approvals_index",
    "insurance:approvals.approve": "insurance:approvals_approve",
    "insurance:approvals.reject": "insurance:approvals_reject",
    
    "insurance:payments.index": "insurance:payments_index",
    "insurance:payments.record": "insurance:record_payment",
    "insurance:payments.online-order": "insurance:create_razorpay_order",
    "insurance:payments.online-success": "insurance:handle_payment_success",
    
    "insurance:profile.update": "insurance:profile",
    
    "insurance:notify.send": "insurance:notify_send",
}

def fix_urls(content):
    for old, new in replacements.items():
        # Match {% url 'old' ... %} or "{{ url('old' ... }}" but only in the {% url %} tags really
        content = content.replace(f"'{old}'", f"'{new}'")
        content = content.replace(f'"{old}"', f'"{new}"')
    return content

for root, _, files in os.walk(tpl_dir):
    for f in files:
        if f.endswith('.html'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = fix_urls(content)
            
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f"Fixed urls in {path}")

print("Done")
