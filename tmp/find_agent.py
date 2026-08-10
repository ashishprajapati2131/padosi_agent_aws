import os
import django

# Setup Django if not already (assuming we are running in shell, this might not be needed, but safe)
from apps.agents.models import Agent

# Find agents linked to a user account, active, with some profile data
agents = Agent.objects.filter(
    user__isnull=False,
    status='active'
).exclude(client_base='').exclude(experience_range='')[:15]

print("=== Potential Agent Accounts ===")
for a in agents:
    print(f"Agent ID: {a.id}")
    print(f"  Email: {a.user.email}")
    print(f"  Fullname: {a.fullname}")
    print(f"  Exp: {a.experience_range}")
    print(f"  Clients: {a.client_base}")
    print("-" * 30)

if not agents:
    print("No agents with full profiles found. Searching for any active agent with a user account...")
    any_agents = Agent.objects.filter(user__isnull=False, status='active')[:5]
    for a in any_agents:
        print(f"Agent ID: {a.id}, Email: {a.user.email}, Fullname: {a.fullname}")
