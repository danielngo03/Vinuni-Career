from __future__ import annotations

import ast
from pathlib import Path

APP = Path(__file__).parents[2] / "app"
BUSINESS_MODULES = {
    "access",
    "institution",
    "students",
    "partners",
    "opportunities",
    "recruitment",
    "engagement",
    "documents",
    "reporting",
    "automation",
}
LAYERS = {"api", "application", "domain", "infrastructure"}


def _python_files(root: Path):
    return (
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
    return imports


def test_required_top_level_architecture_exists():
    for name in {"bootstrap", "shared", "modules", "ai", "platform"}:
        assert (APP / name).is_dir(), f"Missing app/{name}"


def test_business_modules_have_four_layers():
    for module in BUSINESS_MODULES:
        root = APP / "modules" / module
        assert root.is_dir(), f"Missing business module: {module}"
        missing = {layer for layer in LAYERS if not (root / layer).is_dir()}
        assert not missing, f"{module} is missing layers: {sorted(missing)}"


def test_legacy_global_source_packages_are_removed():
    forbidden = {
        "api",
        "core",
        "domain",
        "infra",
        "queue",
        "schemas",
        "services",
        "utils",
        "workers",
    }
    offenders = []
    for name in forbidden:
        root = APP / name
        if root.exists() and any(_python_files(root)):
            offenders.append(name)
    assert not offenders, f"Legacy global packages still contain source: {offenders}"


def test_domain_layers_are_framework_and_infrastructure_free():
    forbidden_prefixes = (
        "fastapi",
        "sqlalchemy",
        "app.bootstrap",
        "app.platform",
    )
    offenders: list[str] = []
    for module in BUSINESS_MODULES:
        for path in _python_files(APP / "modules" / module / "domain"):
            for imported in _imports(path):
                if imported.startswith(forbidden_prefixes):
                    offenders.append(f"{path.relative_to(APP)} -> {imported}")
    assert not offenders, "Domain boundary violations:\n" + "\n".join(offenders)


def test_application_layers_do_not_depend_on_http():
    offenders: list[str] = []
    for module in BUSINESS_MODULES:
        for path in _python_files(APP / "modules" / module / "application"):
            for imported in _imports(path):
                if imported.startswith(("fastapi", "app.bootstrap")):
                    offenders.append(f"{path.relative_to(APP)} -> {imported}")
    assert not offenders, "Application boundary violations:\n" + "\n".join(offenders)


def test_generic_organization_module_was_absorbed_by_institution():
    root = APP / "modules" / "organizations"
    assert not root.exists() or not any(_python_files(root))
