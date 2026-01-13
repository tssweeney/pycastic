# pycastic

Python refactoring CLI tool powered by LibCST.

## Installation

```bash
pip install pycastic
```

## Usage

pycastic uses a unified command interface that automatically detects the operation based on source and target arguments:

```bash
pycastic SOURCE TARGET [OPTIONS]
```

The project root is auto-detected by looking for `pyproject.toml` or `.git` directory, or can be specified with `--root`.

## Operations

### Symbol Operations (source contains `::`)

| Example | Description |
|---------|-------------|
| `pycastic src/utils.py::old_func src/utils.py::new_func` | Rename symbol |
| `pycastic src/utils.py::helper dest.py` | Move symbol |
| `pycastic src/utils.py::helper dest.py::new_name` | Move + rename |
| `pycastic src/utils.py::a,b,c dest.py` | Move multiple symbols |

### File Operations (source is a file path)

| Example | Description |
|---------|-------------|
| `pycastic src/old.py src/new.py` | Rename file |
| `pycastic src/utils.py lib/utils.py` | Move file |
| `pycastic src/utils.py lib/` | Move file to directory |

## Target Formats

| Format | Example | Description |
|--------|---------|-------------|
| `file.py::Symbol` | `utils.py::helper` | Symbol by name |
| `file.py::A,B,C` | `utils.py::foo,bar` | Multiple symbols |
| `file.py:line:col` | `utils.py:10:5` | Symbol at position |

## Options

| Option | Effect |
|--------|--------|
| `--dry-run` / `-n` | Preview changes without applying |
| `--root PATH` / `-r` | Specify project root (auto-detected by default) |
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
pycastic src/utils.py::old_function src/utils.py::new_function

# Rename by position (line:column)
pycastic src/module.py:10:5 src/module.py::new_name
```

### Move symbols

```bash
# Move a function (auto-includes unused internal dependencies)
pycastic src/utils.py::process_data src/processors.py

# Move multiple related functions together
pycastic src/utils.py::parse,validate,transform src/parsers.py

# Preview what would happen
pycastic src/utils.py::my_func dest.py --dry-run
```

### Handling shared dependencies

When moving a symbol that depends on another symbol in the same file, pycastic checks if that dependency is used by other remaining code:

```bash
# If shared dependency detected, you have two options:

# Option 1: Include shared deps in the move
pycastic src/utils.py::func_a dest.py --include-deps

# Option 2: Extract shared deps to a common file (default: utils_common.py)
pycastic src/utils.py::func_a dest.py --shared-file

# Option 3: Extract shared deps to a specific file
pycastic src/utils.py::func_a dest.py --shared-file-path src/common.py
```

### Rename and move files

```bash
# Rename a file (updates all imports)
pycastic src/old_name.py src/new_name.py

# Move a file to a new directory (updates all imports)
pycastic src/utils.py lib/
```

## Claude Code Plugin

pycastic is a shareable Claude Code plugin. Install it via:

```bash
# In Claude Code, use the /plugin command
/plugin install github:tssweeney/pycastic
```

Or add to your project's plugin configuration.

### Plugin Structure

```
pycastic/
├── .claude-plugin/
│   └── plugin.json              # Plugin manifest
├── skills/
│   └── refactoring-python/
│       └── SKILL.md             # Auto-invoked for Python refactoring
├── src/pycastic/                # CLI implementation
└── ...
```

## How It Works

pycastic uses [LibCST](https://github.com/Instagram/LibCST) to parse and transform Python code while preserving formatting. When moving symbols:

1. **Dependency Analysis**: Analyzes what imports and internal symbols the target depends on
2. **Smart Resolution**: Determines which dependencies should move automatically vs. require user input
3. **Import Management**: Updates imports in all affected files
4. **Cleanup**: Removes unused imports from the original file

## License

MIT
