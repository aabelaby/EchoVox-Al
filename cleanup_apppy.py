"""Remove the old HTML template content from app.py."""
import os

path = r'd:\Echovox_fullcode\app.py'

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Keep lines 1-277 (Python code + new route)
# Skip lines 278-3082 (old HTML template + closing """ + old duplicate route)
# Keep lines 3083+ (remaining Flask routes)

# Find the exact boundaries
keep_before = 277  # Lines 1-277 (0-indexed: 0-276)
skip_until = None

# Find the old duplicate route at line ~3080-3082
for i in range(len(lines)-1, 0, -1):
    if 'return render_template_string(HTML_TEMPLATE)' in lines[i]:
        skip_until = i + 1  # Skip up to and including this line
        break

if skip_until is None:
    print("ERROR: Could not find the old render_template_string line!")
    exit(1)

print(f"Keeping lines 1-{keep_before} (Python code + new route)")
print(f"Deleting lines {keep_before+1}-{skip_until} (old template + duplicate route)")
print(f"Keeping lines {skip_until+1}-{len(lines)} (remaining routes)")

new_lines = lines[:keep_before] + ['\n'] + lines[skip_until:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"\nDone! app.py reduced from {len(lines)} lines to {len(new_lines)} lines")
print(f"Removed {len(lines) - len(new_lines)} lines")
