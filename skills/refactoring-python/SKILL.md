---
name: refactoring-python
description: Renames and moves Python symbols and files using pycastic CLI, with automatic import updates across the codebase. Use when refactoring Python code, renaming functions/classes/variables, moving code between files, or reorganizing module structure.
---

# Python Refactoring with pycastic

## Command syntax

```bash
uvx pycastic SOURCE TARGET [OPTIONS]
```

Operation is auto-detected from arguments.

## Symbol operations (source contains `::`)

```bash
# Rename symbol
uvx pycastic file.py::old_name file.py::new_name

# Move symbol to another file
uvx pycastic file.py::symbol dest.py

# Move multiple symbols
uvx pycastic file.py::a,b,c dest.py
```

## File operations

```bash
# Rename file (same directory)
uvx pycastic old.py new.py

# Move file to directory
uvx pycastic file.py dir/
```

## Options

| Option | Effect |
|--------|--------|
| `--dry-run` / `-n` | Preview changes |
| `--include-deps` | Include shared dependencies in move |
| `--shared-file` | Extract shared deps to `{source}_common.py` |

## Shared dependency handling

When moving a symbol that depends on code also used by remaining symbols:

```bash
# Include deps in move (source imports from dest)
uvx pycastic src.py::func_a dest.py --include-deps

# Extract deps to common file
uvx pycastic src.py::func_a dest.py --shared-file
```

## Notes

- Always use `--dry-run` first to preview changes
- Project root auto-detected from `pyproject.toml` or `.git`
