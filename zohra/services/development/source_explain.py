"""Bounded, local structural inspection of project Python code."""

import ast
import hashlib
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field, field_validator


PROJECT = Path(__file__).resolve().parents[3]
MAX_BYTES = 128 * 1024
SYMBOL = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?")


class CodeInspectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(min_length=1, max_length=240)
    symbol: str = Field(default="", max_length=160)

    @field_validator("path")
    @classmethod
    def project_python_path(cls, value):
        if "\\" in value or ":" in value or "\x00" in value:
            raise ValueError("Use a forward-slash project-relative Python path")
        candidate = PurePosixPath(value)
        if (candidate.is_absolute() or not value.startswith("zohra/") or
                not value.endswith(".py") or any(part in {"", ".", ".."} or part.startswith(".") for part in value.split("/"))):
            raise ValueError("Only a project-relative .py file under zohra/ can be inspected")
        return value

    @field_validator("symbol")
    @classmethod
    def python_symbol(cls, value):
        if value and not SYMBOL.fullmatch(value):
            raise ValueError("Use a function, class, or Class.method name")
        return value


def _read_source(root: Path, relative: str):
    root = root.resolve(strict=True)
    target = root.joinpath(*relative.split("/"))
    if not target.resolve(strict=True).is_relative_to(root):
        raise ValueError("Source path escapes the project")
    cursor = root
    for part in relative.split("/"):
        cursor = cursor / part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ValueError("Linked project paths cannot be inspected")
    if not target.is_file():
        raise ValueError("Source path is not a regular file")
    with target.open("rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError("Source file must be a regular file under 128 KB")
        data = source.read(MAX_BYTES + 1)
        after = os.stat(target)
        if len(data) > MAX_BYTES or (before.st_dev, before.st_ino, before.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError("Source file changed or exceeds the read limit")
    return data.decode("utf-8-sig"), hashlib.sha256(data).hexdigest()


def _location(path, node, kind):
    return {"name": node.name, "kind": kind, "line_start": node.lineno,
            "line_end": node.end_lineno, "reference": f"{path}:{node.lineno}"}


def _definitions(path, body):
    return [_location(path, node, "class" if isinstance(node, ast.ClassDef) else "function")
            for node in body if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]


def _imports(tree):
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(("." * node.level) + (node.module or ""))
    return list(dict.fromkeys(names))[:24]


def _signature(node):
    args = node.args
    parameters = [arg.arg for arg in args.posonlyargs + args.args]
    if args.vararg:
        parameters.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        parameters.append("*")
    parameters.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        parameters.append("**" + args.kwarg.arg)
    return f"{node.name}({', '.join(parameters)})"


def _base_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _base_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return "computed base"


def inspect_code(path: str, symbol: str = "", root: Path = PROJECT):
    request = CodeInspectionInput(path=path, symbol=symbol)
    try:
        source, digest = _read_source(Path(root), request.path)
    except (FileNotFoundError, UnicodeError) as error:
        raise ValueError("Source file is missing or is not UTF-8 Python text") from error
    try:
        tree = ast.parse(source, filename=request.path)
    except SyntaxError as error:
        raise ValueError(f"Python syntax error at {request.path}:{error.lineno}: {error.msg}") from error

    names = request.symbol.split(".") if request.symbol else []
    scope = tree.body
    selected = None
    for name in names:
        matches = [node for node in scope if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
        if len(matches) != 1:
            raise ValueError(f"Symbol {request.symbol!r} was not found uniquely in {request.path}")
        selected = matches[0]
        scope = selected.body if isinstance(selected, ast.ClassDef) else []

    if selected is None:
        definitions = _definitions(request.path, tree.body)
        references = definitions[:60]
        imported = _imports(tree)
        summary = (f"{request.path} defines {sum(row['kind'] == 'class' for row in definitions)} classes and "
                   f"{sum(row['kind'] == 'function' for row in definitions)} top-level functions. "
                   f"It imports {', '.join(imported[:8]) or 'no modules'}.")
        kind = "module"
        line_start, line_end = 1, len(source.splitlines())
        signature, calls, branches, returns, raises = "", [], 0, 0, 0
    elif isinstance(selected, ast.ClassDef):
        references = [_location(request.path, selected, "class")] + _definitions(request.path, selected.body)[:40]
        bases = [_base_name(base) for base in selected.bases[:8]]
        summary = (f"Class {selected.name} at {request.path}:{selected.lineno}-{selected.end_lineno} "
                   f"declares {len(references) - 1} methods or nested definitions" +
                   (f" and inherits {', '.join(bases)}." if bases else "."))
        kind = "class"
        line_start, line_end = selected.lineno, selected.end_lineno
        signature, calls, branches, returns, raises = selected.name, [], 0, 0, 0
    else:
        references = [_location(request.path, selected, "function")]
        nodes = list(ast.walk(selected))
        calls = list(dict.fromkeys(
            item.func.id if isinstance(item.func, ast.Name) else item.func.attr
            for item in nodes if isinstance(item, ast.Call) and isinstance(item.func, (ast.Name, ast.Attribute))))[:20]
        branches = sum(isinstance(item, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match)) for item in nodes)
        returns = sum(isinstance(item, ast.Return) for item in nodes)
        raises = sum(isinstance(item, ast.Raise) for item in nodes)
        signature = _signature(selected)
        summary = (f"{'Async function' if isinstance(selected, ast.AsyncFunctionDef) else 'Function'} {signature} "
                   f"is defined at {request.path}:{selected.lineno}-{selected.end_lineno}. "
                   f"Its source contains {branches} branches or loops, {returns} return statements, "
                   f"and {raises} explicit raises." +
                   (f" It calls {', '.join(calls[:8])}." if calls else ""))
        kind = "function"
        line_start, line_end = selected.lineno, selected.end_lineno

    return {"source": "local Python AST", "observed_at": datetime.now(timezone.utc).isoformat(),
            "path": request.path, "symbol": request.symbol, "kind": kind, "line_start": line_start,
            "line_end": line_end, "summary": summary, "signature": signature, "imports": _imports(tree),
            "calls": calls, "branches": branches, "returns": returns, "raises": raises,
            "references": references, "sha256": digest, "static_only": True,
            "limitations": "Static Python structure only. No code executed, LLM upload, behavior proof, or edits."}
