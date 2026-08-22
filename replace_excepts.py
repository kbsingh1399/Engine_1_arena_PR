import re

with open('Engine_1.py', 'r', encoding='utf-8') as f:
    content = f.read()

count = 0
def repl(m):
    global count
    count += 1
    indent = m.group(1)
    exc_part = m.group(2)
    if exc_part.strip() == 'except:':
        exc_part = 'except Exception as e:'
    elif not ' as ' in exc_part:
        exc_part = exc_part.replace(':', ' as e:')
    
    return f'{indent}{exc_part}\n{indent}    print(f"[WARN] Swallowed exception: {{e}}")\n'

new_content, n1 = re.subn(r'([ \t]*)(except[^\n]*:)[ \t]*\n[ \t]*pass[ \t]*(?:\n|$)', repl, content)

print(f'Replaced {n1} occurrences.')
with open('Engine_1.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
