import ast
from collections import defaultdict
from pathlib import Path
import unittest


APP_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAMES = {
    "configs",
    "experiments",
    "hardware",
    "localization",
    "map",
    "planner",
    "runtime",
    "shared",
    "storage",
    "web",
}
ALLOWED_DEPENDENCIES = {
    "configs": set(),
    "experiments": {"localization", "map", "runtime", "shared", "storage"},
    "hardware": {"planner"},
    "localization": {"shared"},
    "map": set(),
    "planner": set(),
    "runtime": {"hardware", "localization", "planner", "shared"},
    "shared": set(),
    "storage": set(),
    "web": {"hardware", "localization", "planner", "shared", "storage"},
}


class PackageImportTests(unittest.TestCase):
    def test_internal_cross_module_imports_are_package_qualified(self):
        violations = []
        for path in APP_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    modules = [node.module]
                else:
                    continue
                for module in modules:
                    root = module.split(".", 1)[0]
                    if root in MODULE_NAMES and not module.startswith("Integrated_version."):
                        violations.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}: {module}")

        self.assertEqual(violations, [])

    def test_domain_dependencies_are_acyclic_and_respect_layer_boundaries(self):
        graph = defaultdict(set)
        for path in APP_ROOT.rglob("*.py"):
            owner = path.relative_to(APP_ROOT).parts[0]
            if owner not in MODULE_NAMES:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = [node.module]
                else:
                    continue
                for name in imported:
                    prefix = "Integrated_version."
                    if name.startswith(prefix):
                        target = name[len(prefix):].split(".", 1)[0]
                        if target in MODULE_NAMES and target != owner:
                            graph[owner].add(target)

        visited = set()
        active = set()

        def has_cycle(module):
            if module in active:
                return True
            if module in visited:
                return False
            active.add(module)
            if any(has_cycle(dependency) for dependency in graph[module]):
                return True
            active.remove(module)
            visited.add(module)
            return False

        self.assertFalse(any(has_cycle(module) for module in MODULE_NAMES))
        self.assertEqual(graph["shared"], set())
        self.assertNotIn("experiments", graph["runtime"])
        self.assertFalse(graph["storage"] & {"experiments", "runtime", "web"})
        violations = {
            f"{module} -> {dependency}"
            for module, dependencies in graph.items()
            for dependency in dependencies - ALLOWED_DEPENDENCIES[module]
        }
        self.assertEqual(violations, set())


if __name__ == "__main__":
    unittest.main()
