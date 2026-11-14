"""Produce a per-file static audit inventory without importing application code."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.venv', 'node_modules', '__pycache__', '.pytest_cache', 'logs', 'chroma_db', 'chroma_db_a'}
rows = []
def visit(folder):
    try:
        children = sorted(folder.iterdir())
    except PermissionError:
        return
    for path in children:
        if path.name in SKIP or path.is_symlink():
            continue
        if path.is_dir():
            visit(path)
        elif path.suffix in {'.py', '.js', '.html', '.css'}:
            relative = path.relative_to(ROOT).as_posix()
            source = path.read_text(encoding='utf-8-sig', errors='replace')
            markers = []
            error = None
            if path.suffix == '.py':
                try:
                    tree = ast.parse(source, filename=relative)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            body = [n for n in node.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant) or not isinstance(n.value.value, str)]
                            if len(body) == 1 and isinstance(body[0], ast.Pass):
                                markers.append({'line': node.lineno, 'kind': 'empty function', 'name': node.name})
                except SyntaxError as exc:
                    error = str(exc)
            for line, text in enumerate(source.splitlines(), 1):
                if re.search(r'\b(TODO|FIXME|NotImplementedError|stub|mock|placeholder)\b', text, re.I):
                    markers.append({'line': line, 'kind': 'review marker', 'text': text.strip()[:180]})
            rows.append({'file': relative, 'lines': len(source.splitlines()),
                         'scope': 'archive/copy' if relative.startswith(('trading_bot2/', 'zohra_backups/')) else 'active/test/tool',
                         'syntax_error': error, 'markers': markers})

visit(ROOT)
destination = ROOT / 'scratch' / 'audit-inventory.json'
destination.write_text(json.dumps(rows, indent=2), encoding='utf-8')
print(json.dumps({'files': len(rows), 'syntax_errors': [r for r in rows if r['syntax_error']],
                  'files_with_markers': sum(bool(r['markers']) for r in rows),
                  'active_files': sum(r['scope'] == 'active/test/tool' for r in rows)}, indent=2))
