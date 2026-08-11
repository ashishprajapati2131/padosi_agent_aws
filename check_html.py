import urllib.request
html = urllib.request.urlopen('http://127.0.0.1:1234/find-agents/').read().decode('utf-8')
end_idx = html.find('<!-- Comparison Bar -->')
print(html[end_idx-200:end_idx+50])
