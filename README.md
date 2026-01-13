# pycastic

Python refactoring CLI tool powered by LibCST.

## Installation

```bash
pip install pycastic
```

## Commands

| Command | Description |
|---------|-------------|
| `pycastic rename ROOT TARGET NEW_NAME` | Rename a symbol across the codebase |
| `pycastic move ROOT TARGET DEST_FILE` | Move symbol(s) to another file |
| `pycastic rename-file ROOT FILE NEW_NAME` | Rename a file and update imports |
| `pycastic move-file ROOT FILE DEST_DIR` | Move a file and update imports |

## Target Formats

| Format | Example | Description |
|--------|---------|-------------|
| `file.py::Symbol` | `utils.py::helper` | Symbol by name |
| `file.py::A,B,C` | `utils.py::foo,bar` | Multiple symbols |
| `file.py:line:col` | `utils.py:10:5` | Symbol at position |

## Move Command Options

| Option | Effect |
|--------|--------|
| `--dry-run` / `-n` | Preview changes without applying |
| `--include-deps` | Auto-include shared dependencies in the move |
| `--shared-file` | Extract shared deps to default file (`{source}_common.py`) |
| `--shared-file-path PATH` | Extract shared deps to specified file |

## Move Behavior Rules

| Scenario | Behavior |
|----------|----------|
| Symbol uses external imports | Imports copied to destination |
| Symbol uses internal dep (unused elsewhere) | Dep moved automatically |
| Symbol uses internal dep (used elsewhere) | Error: use `--include-deps` or `--shared-file` |
| Other files import moved symbol | Imports updated to new location |
| Original file uses moved symbol | Import added from new location |
| Original file has unused imports after move | Unused imports removed |

## Examples

### Rename a symbol

```bash
# Rename by name
pycastic rename . src/utils.py::old_function new_function

# Rename by position (line:column)
pycastic rename /path/to/project src/module.py:10:5 new_name
```

### Move symbols

```bash
# Move a function (auto-includes unused internal dependencies)
pycastic move . src/utils.py::process_data src/processors.py

# Move multiple related functions together
pycastic move . src/utils.py::parse,validate,transform src/parsers.py

# Preview what would happen
pycastic move . src/utils.py::my_func dest.py --dry-run
```

### Handling shared dependencies

When moving a symbol that depends on another symbol in the same file, pycastic checks if that dependency is used by other remaining code:

```bash
# If shared dependency detected, you have two options:

# Option 1: Include shared deps in the move
pycastic move . src/utils.py::func_a dest.py --include-deps

# Option 2: Extract shared deps to a common file (default: utils_common.py)
pycastic move . src/utils.py::func_a dest.py --shared-file

# Option 3: Extract shared deps to a specific file
pycastic move . src/utils.py::func_a dest.py --shared-file-path src/common.py
```

### Rename and move files

```bash
# Rename a file (updates all imports)
pycastic rename-file . src/old_name.py new_name

# Move a file to a new directory (updates all imports)
pycastic move-file . src/utils.py src/lib/
```

## How It Works

pycastic uses [LibCST](https://github.com/Instagram/LibCST) to parse and transform Python code while preserving formatting. When moving symbols:

1. **Dependency Analysis**: Analyzes what imports and internal symbols the target depends on
2. **Smart Resolution**: Determines which dependencies should move automatically vs. require user input
3. **Import Management**: Updates imports in all affected files
4. **Cleanup**: Removes unused imports from the original file

## License

MIT
