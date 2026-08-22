lines = open('templates/agents/edit_profile.html', encoding='utf-8').readlines()
end = [i for i, l in enumerate(lines) if 'id="portfolio-content"' in l][0]
for i in range(end-10, end+10):
    print(f"{i+1} {lines[i].rstrip()}")
