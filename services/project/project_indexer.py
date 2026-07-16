from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True, frozen=True)
class PythonSymbol:
    name: str
    kind: str
    line_number: int


@dataclass(slots=True)
class PythonFileIndex:
    path: str
    imports: list[str] = field(default_factory=list)
    symbols: list[PythonSymbol] = field(default_factory=list)
    error: str | None = None


class ProjectIndexer:
    """
    Builds a lightweight structural index of Python source files.

    Extracts:
    - imports
    - classes
    - functions
    - async functions
    - class methods

    It never executes project code.
    """

    DEFAULT_EXCLUDED_DIRECTORIES = {
        ".git",
        ".atlas_data",
        ".atlas_staging",
        ".atlas_apply_project",
        "venv",
        "__pycache__",
        "node_modules",
    }

    def __init__(
        self,
        excluded_directories: set[str] | None = None,
        max_files: int = 500,
    ) -> None:
        if max_files < 1:
            raise ValueError("max_files must be at least 1.")

        self.excluded_directories = (
            excluded_directories
            or self.DEFAULT_EXCLUDED_DIRECTORIES.copy()
        )
        self.max_files = max_files

    def index_project(
        self,
        root: str | Path,
    ) -> list[PythonFileIndex]:
        root_path = Path(root).resolve()

        if not root_path.exists():
            raise FileNotFoundError(
                f"Project root does not exist: {root_path}"
            )

        if not root_path.is_dir():
            raise NotADirectoryError(
                f"Project root is not a directory: {root_path}"
            )

        python_files = [
            path
            for path in sorted(root_path.rglob("*.py"))
            if not self._is_excluded(path, root_path)
        ]

        return [
            self.index_file(
                path=path,
                root=root_path,
            )
            for path in python_files[: self.max_files]
        ]

    def index_file(
        self,
        path: str | Path,
        root: str | Path | None = None,
    ) -> PythonFileIndex:
        file_path = Path(path).resolve()
        root_path = (
            Path(root).resolve()
            if root is not None
            else file_path.parent
        )

        try:
            relative_path = str(
                file_path.relative_to(root_path)
            )
        except ValueError:
            relative_path = str(file_path)

        try:
            source = file_path.read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeError) as exc:
            return PythonFileIndex(
                path=relative_path,
                error=f"Unable to read file: {exc}",
            )

        try:
            syntax_tree = ast.parse(
                source,
                filename=str(file_path),
            )
        except SyntaxError as exc:
            location = (
                f"line {exc.lineno}"
                if exc.lineno is not None
                else "unknown line"
            )

            return PythonFileIndex(
                path=relative_path,
                error=(
                    f"SyntaxError at {location}: "
                    f"{exc.msg}"
                ),
            )

        imports = self._extract_imports(syntax_tree)
        symbols = self._extract_symbols(syntax_tree)

        return PythonFileIndex(
            path=relative_path,
            imports=imports,
            symbols=symbols,
        )

    def render(
        self,
        indexes: list[PythonFileIndex],
    ) -> str:
        sections: list[str] = []

        for file_index in indexes:
            lines = [file_index.path]

            if file_index.error:
                lines.append(
                    f"  ! ERROR: {file_index.error}"
                )
                sections.append("\n".join(lines))
                continue

            if file_index.imports:
                lines.append("  imports:")

                for imported_module in file_index.imports:
                    lines.append(
                        f"    - {imported_module}"
                    )

            if file_index.symbols:
                lines.append("  symbols:")

                for symbol in file_index.symbols:
                    lines.append(
                        "    - "
                        f"{symbol.kind}: {symbol.name} "
                        f"(line {symbol.line_number})"
                    )

            if not file_index.imports and not file_index.symbols:
                lines.append(
                    "  no imports or top-level symbols"
                )

            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    def build_index_text(
        self,
        root: str | Path,
    ) -> str:
        return self.render(
            self.index_project(root)
        )

    def _is_excluded(
        self,
        path: Path,
        root: Path,
    ) -> bool:
        try:
            relative_parts = path.relative_to(root).parts
        except ValueError:
            relative_parts = path.parts

        return any(
            part in self.excluded_directories
            for part in relative_parts
        )

    @staticmethod
    def _extract_imports(
        syntax_tree: ast.AST,
    ) -> list[str]:
        imports: set[str] = set()

        for node in ast.walk(syntax_tree):
            if isinstance(node, ast.Import):
                imports.update(
                    alias.name
                    for alias in node.names
                )

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""

                imported_names = ", ".join(
                    alias.name
                    for alias in node.names
                )

                if module:
                    imports.add(
                        f"{module}: {imported_names}"
                    )
                else:
                    imports.add(imported_names)

        return sorted(imports)

    @classmethod
    def _extract_symbols(
        cls,
        syntax_tree: ast.Module,
    ) -> list[PythonSymbol]:
        symbols: list[PythonSymbol] = []

        for node in syntax_tree.body:
            if isinstance(node, ast.ClassDef):
                symbols.append(
                    PythonSymbol(
                        name=node.name,
                        kind="class",
                        line_number=node.lineno,
                    )
                )

                symbols.extend(
                    cls._extract_class_methods(node)
                )

            elif isinstance(node, ast.FunctionDef):
                symbols.append(
                    PythonSymbol(
                        name=node.name,
                        kind="function",
                        line_number=node.lineno,
                    )
                )

            elif isinstance(node, ast.AsyncFunctionDef):
                symbols.append(
                    PythonSymbol(
                        name=node.name,
                        kind="async_function",
                        line_number=node.lineno,
                    )
                )

        return symbols

    @staticmethod
    def _extract_class_methods(
        class_node: ast.ClassDef,
    ) -> list[PythonSymbol]:
        methods: list[PythonSymbol] = []

        for node in class_node.body:
            if isinstance(node, ast.FunctionDef):
                methods.append(
                    PythonSymbol(
                        name=f"{class_node.name}.{node.name}",
                        kind="method",
                        line_number=node.lineno,
                    )
                )

            elif isinstance(node, ast.AsyncFunctionDef):
                methods.append(
                    PythonSymbol(
                        name=f"{class_node.name}.{node.name}",
                        kind="async_method",
                        line_number=node.lineno,
                    )
                )

        return methods
