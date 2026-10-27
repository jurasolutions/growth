"""A static call graph of `jura_growth`, for structural tests (test strategy v3 G34).

Each node is a function, as `(module, qualname)`: `("jura_growth.approvals", "request")`, or
`("jura_growth.agents.publish", "register.<locals>.done")` for a command defined inside a plug-in's
`register()`. An edge is any reference from one function's body to another that the source alone
can resolve: a bare name (a local def, a module-level def, or an imported function, followed
through re-exports), `module.function` and `package.module.function` through the imports, and
`self.method` or `cls.method` inside a class. A reference counts whether or not it is called, so a
function handed to a helper is an edge too.

What it can't see: calls through an object it can't type (a kind's hooks, reached as
`registered.kind.on_approve`), `getattr`, and subprocesses. So a path it finds is real, and a path
it misses may exist. A test that relies on "no path" should also pin the places it starts from.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "jura_growth"

Node = tuple[str, str]


class _Module:
    def __init__(self, path: Path):
        relative = path.relative_to(PACKAGE.parent).with_suffix("").parts
        self.is_package = path.name == "__init__.py"
        self.name = ".".join(relative[:-1] if self.is_package else relative)
        self.tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        self.aliases: dict[str, tuple[str, ...]] = {}  # ("module", m) or ("from", m, name)
        self.functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        self._imports()
        self._defs(self.tree, "")

    def _base(self, node: ast.ImportFrom) -> str:
        if not node.level:
            return node.module or ""
        parts = self.name.split(".")
        if not self.is_package:
            parts = parts[:-1]
        parts = parts[: len(parts) - (node.level - 1)]
        return ".".join([*parts, *([node.module] if node.module else [])])

    def _imports(self) -> None:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        self.aliases[alias.asname] = ("module", alias.name)
                    else:
                        self.aliases.setdefault(alias.name.split(".")[0], ("module", alias.name.split(".")[0]))
            elif isinstance(node, ast.ImportFrom):
                base = self._base(node)
                for alias in node.names:
                    self.aliases[alias.asname or alias.name] = ("from", base, alias.name)

    def _defs(self, node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                self.functions[qualname] = child
                self._defs(child, f"{qualname}.<locals>.")
            elif isinstance(child, ast.ClassDef):
                self._defs(child, f"{prefix}{child.name}.")
            else:
                self._defs(child, prefix)


class CallGraph:
    def __init__(self) -> None:
        found = (_Module(path) for path in sorted(PACKAGE.rglob("*.py")))
        self.modules = {module.name: module for module in found}
        self.edges: dict[Node, set[Node]] = {
            (module.name, qualname): self._references(module, qualname, function)
            for module in self.modules.values()
            for qualname, function in module.functions.items()
        }

    # --- resolving a name ---------------------------------------------------------------

    def _attribute(self, module_name: str, attr: str, depth: int = 0) -> tuple[str, str] | None:
        """`module.attr` as a function node, or ("module", name) for a submodule."""
        module = self.modules.get(module_name)
        if module is None or depth > 8:
            return None
        if attr in module.functions:
            return (module_name, attr)
        if f"{module_name}.{attr}" in self.modules:
            return ("module", f"{module_name}.{attr}")
        alias = module.aliases.get(attr)
        if alias is None:
            return None
        if alias[0] == "module":
            return ("module", alias[1])
        return self._attribute(alias[1], alias[2], depth + 1)

    def _name(self, module: _Module, qualname: str, name: str) -> tuple[str, str] | None:
        scope = qualname
        while True:  # a def in an enclosing function, innermost first
            local = f"{scope}.<locals>.{name}"
            if local in module.functions:
                return (module.name, local)
            if ".<locals>." not in scope:
                break
            scope = scope.rsplit(".<locals>.", 1)[0]
        if name in module.functions:
            return (module.name, name)
        alias = module.aliases.get(name)
        if alias is None:
            return None
        if alias[0] == "module":
            return ("module", alias[1])
        if f"{alias[1]}.{alias[2]}" in self.modules:
            return ("module", f"{alias[1]}.{alias[2]}")
        return self._attribute(alias[1], alias[2])

    def _references(self, module: _Module, qualname: str, function: ast.AST) -> set[Node]:
        owner = qualname.rsplit(".", 1)[0] if "." in qualname else None
        if owner and owner.endswith(">"):
            owner = None  # a nested function, not a method
        found: set[Node] = set()
        for node in ast.walk(function):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                target = self._name(module, qualname, node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                chain: list[str] = []
                value: ast.AST = node
                while isinstance(value, ast.Attribute):
                    chain.insert(0, value.attr)
                    value = value.value
                if not isinstance(value, ast.Name):
                    continue
                if value.id in ("self", "cls") and owner:
                    method = f"{owner}.{chain[0]}"
                    target = (module.name, method) if method in module.functions else None
                else:
                    target = self._name(module, qualname, value.id)
                    for attr in chain:
                        if target is None or target[0] != "module":
                            break
                        target = self._attribute(target[1], attr)
            else:
                continue
            if target is not None and target[0] != "module":
                found.add(target)
        return found

    # --- questions ----------------------------------------------------------------------

    def reaches(self, start: Node, goal: Node, *, avoiding: frozenset[Node] = frozenset()) -> bool:
        """Whether some path leads from `start` to `goal` without passing through `avoiding`."""
        seen: set[Node] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == goal:
                return True
            if node in seen or node in avoiding:
                continue
            seen.add(node)
            stack.extend(self.edges.get(node, ()))
        return False

    def callers_of(self, goal: Node) -> set[Node]:
        """The functions whose own body refers to `goal`."""
        return {node for node, targets in self.edges.items() if goal in targets}


@cache
def graph() -> CallGraph:
    return CallGraph()
