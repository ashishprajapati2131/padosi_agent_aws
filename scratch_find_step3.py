lines = open('templates/agents/edit_profile.html', encoding='utf-8').readlines()
end = [i for i, l in enumerate(lines) if 'id="step-3"' in l][0]
for i in range(end, end+30):
    print(f"{i+1} {lines[i].rstrip()}")
