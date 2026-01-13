"""Tests for the refactor module, specifically relative import handling."""
import pytest

from pycastic.refactor import (
    _make_dotted_name,
    _parse_relative_module,
    add_import,
)


class TestMakeDottedName:
    """Tests for _make_dotted_name function."""

    def test_simple_name(self):
        """Test creating a simple name."""
        result = _make_dotted_name("foo")
        assert result.value == "foo"

    def test_dotted_name(self):
        """Test creating a dotted name."""
        import libcst as cst

        result = _make_dotted_name("foo.bar")
        assert isinstance(result, cst.Attribute)
        assert result.attr.value == "bar"
        assert result.value.value == "foo"

    def test_deeply_nested_name(self):
        """Test creating a deeply nested dotted name."""
        import libcst as cst

        result = _make_dotted_name("foo.bar.baz")
        assert isinstance(result, cst.Attribute)
        assert result.attr.value == "baz"

    def test_empty_string_raises_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            _make_dotted_name("")

    def test_single_dot_raises_error(self):
        """Test that single dot raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            _make_dotted_name(".")

    def test_multiple_dots_raises_error(self):
        """Test that multiple dots only raises ValueError."""
        with pytest.raises(ValueError, match="empty"):
            _make_dotted_name("..")


class TestParseRelativeModule:
    """Tests for _parse_relative_module function."""

    def test_absolute_module(self):
        """Test parsing an absolute module."""
        import libcst as cst

        relative, module = _parse_relative_module("foo.bar")
        assert relative == []
        assert isinstance(module, cst.Attribute)

    def test_simple_absolute_module(self):
        """Test parsing a simple absolute module."""
        import libcst as cst

        relative, module = _parse_relative_module("foo")
        assert relative == []
        assert isinstance(module, cst.Name)
        assert module.value == "foo"

    def test_single_dot_relative(self):
        """Test parsing single dot relative import (from . import x)."""
        import libcst as cst

        relative, module = _parse_relative_module(".")
        assert len(relative) == 1
        assert all(isinstance(d, cst.Dot) for d in relative)
        assert module is None

    def test_double_dot_relative(self):
        """Test parsing double dot relative import (from .. import x)."""
        import libcst as cst

        relative, module = _parse_relative_module("..")
        assert len(relative) == 2
        assert all(isinstance(d, cst.Dot) for d in relative)
        assert module is None

    def test_relative_with_module(self):
        """Test parsing relative import with module (from .foo import x)."""
        import libcst as cst

        relative, module = _parse_relative_module(".foo")
        assert len(relative) == 1
        assert isinstance(module, cst.Name)
        assert module.value == "foo"

    def test_double_dot_with_module(self):
        """Test parsing double dot relative with module (from ..foo.bar import x)."""
        import libcst as cst

        relative, module = _parse_relative_module("..foo.bar")
        assert len(relative) == 2
        assert isinstance(module, cst.Attribute)


class TestAddImport:
    """Tests for add_import function with relative imports."""

    def test_add_absolute_import(self):
        """Test adding an absolute import."""
        source = '"""Module."""\n\ndef foo():\n    pass\n'
        result = add_import(source, "os.path", "join")
        assert "from os.path import join" in result

    def test_add_single_dot_relative_import(self):
        """Test adding a single dot relative import (from . import x)."""
        source = '"""Module."""\n\ndef foo():\n    pass\n'
        result = add_import(source, ".", "helper")
        assert "from . import helper" in result

    def test_add_double_dot_relative_import(self):
        """Test adding a double dot relative import (from .. import x)."""
        source = '"""Module."""\n\ndef foo():\n    pass\n'
        result = add_import(source, "..", "helper")
        assert "from .. import helper" in result

    def test_add_relative_import_with_module(self):
        """Test adding a relative import with module (from .foo import x)."""
        source = '"""Module."""\n\ndef foo():\n    pass\n'
        result = add_import(source, ".utils", "helper")
        assert "from .utils import helper" in result

    def test_add_double_dot_relative_with_module(self):
        """Test adding double dot relative with module (from ..foo import x)."""
        source = '"""Module."""\n\ndef foo():\n    pass\n'
        result = add_import(source, "..utils", "helper")
        assert "from ..utils import helper" in result

    def test_add_import_with_alias(self):
        """Test adding an import with an alias."""
        source = '"""Module."""\n\ndef foo():\n    pass\n'
        result = add_import(source, "datetime", "datetime", alias="dt")
        assert "from datetime import datetime as dt" in result

    def test_add_import_after_existing(self):
        """Test that new imports are added after existing imports."""
        source = '"""Module."""\nimport os\n\ndef foo():\n    pass\n'
        result = add_import(source, "sys", "exit")
        lines = result.splitlines()
        # New import should be after 'import os'
        os_idx = next(i for i, l in enumerate(lines) if "import os" in l)
        sys_idx = next(i for i, l in enumerate(lines) if "from sys import exit" in l)
        assert sys_idx > os_idx


class TestMoveSymbolWithRelativeImports:
    """Integration tests for move_symbol with relative imports."""

    def test_move_symbol_with_relative_import_dependency(self, tmp_path):
        """Test moving a symbol that has relative import dependencies."""
        from pycastic.core import move_symbol
        from pycastic.parsing import parse_target

        # Create a package structure
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text('"""Package."""\n')

        # Create module with relative import
        (pkg / "utils.py").write_text('''"""Utils module."""
from . import helpers


def my_func():
    return helpers.do_something()


def other_func():
    return 42
''')

        # Create the helpers module
        (pkg / "helpers.py").write_text('''"""Helpers module."""


def do_something():
    return 1
''')

        # Create destination
        (pkg / "dest.py").write_text('"""Destination module."""\n')

        # Move my_func - should preserve the relative import
        target = parse_target("pkg/utils.py::my_func")
        result, info = move_symbol(tmp_path, target, tmp_path / "pkg" / "dest.py", dry_run=False)

        # Check destination has the function and relative import
        dest_content = (pkg / "dest.py").read_text()
        assert "def my_func" in dest_content
        # The import should be present (either relative or absolute)
        assert "helpers" in dest_content


class TestEdgeCases:
    """Edge case tests for import handling."""

    def test_parse_syntax_error_fallback(self):
        """Test that add_import handles unparseable source gracefully."""
        # Source with syntax error
        source = "def broken(:\n    pass"
        result = add_import(source, "os", "path")
        # Should prepend import and return
        assert "from os import path" in result
        assert "def broken(:" in result

    def test_empty_source(self):
        """Test adding import to empty source."""
        source = ""
        result = add_import(source, "os", "path")
        assert "from os import path" in result
