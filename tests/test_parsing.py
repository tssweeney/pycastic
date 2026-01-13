"""Tests for the parsing module."""
from pathlib import Path

import pytest

from pycastic.errors import SymbolNotFoundError, TargetParseError
from pycastic.parsing import (
    NAME_PATTERN,
    POSITION_PATTERN,
    SymbolByName,
    SymbolByPosition,
    find_symbol_offset,
    parse_target,
)


class TestParseTarget:
    """Tests for parse_target function."""

    def test_parse_symbol_by_name(self):
        """Test parsing file.py::SymbolName format."""
        result = parse_target("src/module.py::MyClass")
        assert isinstance(result, SymbolByName)
        assert result.file_path == Path("src/module.py")
        assert result.symbol_name == "MyClass"

    def test_parse_symbol_by_name_nested_path(self):
        """Test parsing with nested directory path."""
        result = parse_target("src/pkg/subpkg/module.py::func")
        assert isinstance(result, SymbolByName)
        assert result.file_path == Path("src/pkg/subpkg/module.py")
        assert result.symbol_name == "func"

    def test_parse_symbol_by_position(self):
        """Test parsing file.py:line:column format."""
        result = parse_target("module.py:10:5")
        assert isinstance(result, SymbolByPosition)
        assert result.file_path == Path("module.py")
        assert result.line == 10
        assert result.column == 5

    def test_parse_symbol_by_position_nested_path(self):
        """Test parsing position format with nested path."""
        result = parse_target("src/utils/helpers.py:100:0")
        assert isinstance(result, SymbolByPosition)
        assert result.file_path == Path("src/utils/helpers.py")
        assert result.line == 100
        assert result.column == 0

    def test_parse_invalid_format_raises(self):
        """Test that invalid formats raise TargetParseError."""
        with pytest.raises(TargetParseError) as exc_info:
            parse_target("invalid")
        assert "Invalid target format" in str(exc_info.value)

    def test_parse_single_colon_raises(self):
        """Test that single colon format raises."""
        with pytest.raises(TargetParseError):
            parse_target("module.py:Symbol")

    def test_parse_empty_string_raises(self):
        """Test that empty string raises."""
        with pytest.raises(TargetParseError):
            parse_target("")

    def test_parse_non_py_file_raises(self):
        """Test that non-.py files raise."""
        with pytest.raises(TargetParseError):
            parse_target("module.txt::Symbol")


class TestFindSymbolOffset:
    """Tests for find_symbol_offset function."""

    def test_find_function(self):
        """Test finding a function definition."""
        content = '''def my_function():
    pass
'''
        offset = find_symbol_offset(content, "my_function")
        assert content[offset : offset + 11] == "my_function"

    def test_find_class(self):
        """Test finding a class definition."""
        content = '''class MyClass:
    pass
'''
        offset = find_symbol_offset(content, "MyClass")
        assert content[offset : offset + 7] == "MyClass"

    def test_find_async_function(self):
        """Test finding an async function definition."""
        content = '''async def async_func():
    pass
'''
        offset = find_symbol_offset(content, "async_func")
        assert content[offset : offset + 10] == "async_func"

    def test_find_variable(self):
        """Test finding a variable assignment."""
        content = '''MY_CONSTANT = 42
'''
        offset = find_symbol_offset(content, "MY_CONSTANT")
        assert content[offset : offset + 11] == "MY_CONSTANT"

    def test_find_with_leading_code(self):
        """Test finding symbol with code before it."""
        content = '''import os

def first():
    pass

def second():
    pass
'''
        offset = find_symbol_offset(content, "second")
        assert content[offset : offset + 6] == "second"

    def test_symbol_not_found_raises(self):
        """Test that missing symbol raises SymbolNotFoundError."""
        content = '''def existing():
    pass
'''
        with pytest.raises(SymbolNotFoundError) as exc_info:
            find_symbol_offset(content, "nonexistent")
        assert "nonexistent" in str(exc_info.value)


class TestRegexPatterns:
    """Tests for the regex patterns."""

    def test_name_pattern_matches(self):
        """Test NAME_PATTERN matches valid inputs."""
        assert NAME_PATTERN.match("file.py::Symbol")
        assert NAME_PATTERN.match("path/to/file.py::_private")
        assert NAME_PATTERN.match("a.py::A")

    def test_name_pattern_rejects(self):
        """Test NAME_PATTERN rejects invalid inputs."""
        assert not NAME_PATTERN.match("file.py:Symbol")
        assert not NAME_PATTERN.match("file.txt::Symbol")
        assert not NAME_PATTERN.match("file.py::")

    def test_position_pattern_matches(self):
        """Test POSITION_PATTERN matches valid inputs."""
        assert POSITION_PATTERN.match("file.py:1:0")
        assert POSITION_PATTERN.match("path/to/file.py:100:50")
        assert POSITION_PATTERN.match("a.py:1:1")

    def test_position_pattern_rejects(self):
        """Test POSITION_PATTERN rejects invalid inputs."""
        assert not POSITION_PATTERN.match("file.py:1")
        assert not POSITION_PATTERN.match("file.py:a:b")
        assert not POSITION_PATTERN.match("file.txt:1:0")
