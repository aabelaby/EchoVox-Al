"""Extract CSS, JS, and HTML from app.py into separate files."""
import re, os

base = r'd:\Echovox_fullcode'
os.makedirs(os.path.join(base, 'static', 'css'), exist_ok=True)
os.makedirs(os.path.join(base, 'static', 'js'), exist_ok=True)
os.makedirs(os.path.join(base, 'templates'), exist_ok=True)

with open(os.path.join(base, 'app.py'), 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

# Find the HTML_TEMPLATE string boundaries
template_start = None
template_end = None
for i, line in enumerate(lines):
    if 'HTML_TEMPLATE = """' in line:
        template_start = i
    if template_start is not None and i > template_start and line.strip() == '"""':
        template_end = i
        break

print(f"Template: lines {template_start+1} to {template_end+1}")

# Extract the template content (between the triple quotes)
template_lines = lines[template_start+1:template_end]
template_content = '\n'.join(template_lines)

# Extract CSS (between <style> and </style>)
css_match = re.search(r'<style>(.*?)</style>', template_content, re.DOTALL)
css_content = css_match.group(1).strip() if css_match else ''

# Extract JS (between last <script> and </script> - the main app script, not CDN links)
script_matches = list(re.finditer(r'<script>(.*?)</script>', template_content, re.DOTALL))
js_content = script_matches[-1].group(1).strip() if script_matches else ''

# Write CSS
with open(os.path.join(base, 'static', 'css', 'style.css'), 'w', encoding='utf-8') as f:
    f.write(css_content)
print(f"CSS written: {len(css_content)} chars, {css_content.count(chr(10))+1} lines")

# Write JS
with open(os.path.join(base, 'static', 'js', 'app.js'), 'w', encoding='utf-8') as f:
    f.write(js_content)
print(f"JS written: {len(js_content)} chars, {js_content.count(chr(10))+1} lines")

# Now create index.html by replacing inline style/script with links
html_content = template_content

# Replace <style>...</style> with CSS link
html_content = re.sub(
    r'    <style>.*?</style>',
    '    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/style.css\') }}">',
    html_content,
    count=1,
    flags=re.DOTALL
)

# Replace the main <script>...</script> (last one) with JS link
parts = list(re.finditer(r'<script>(.*?)</script>', html_content, re.DOTALL))
if parts:
    last_script = parts[-1]
    html_content = (
        html_content[:last_script.start()] +
        '<script src="{{ url_for(\'static\', filename=\'js/app.js\') }}"></script>' +
        html_content[last_script.end():]
    )

# Write HTML template
with open(os.path.join(base, 'templates', 'index.html'), 'w', encoding='utf-8') as f:
    f.write(html_content)
print(f"HTML written: {len(html_content)} chars, {html_content.count(chr(10))+1} lines")

print("\nDone! All files extracted successfully.")
