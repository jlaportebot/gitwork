# gitwork

CLI tool for managing git worktrees with ease.

## Features

- Create, list, and remove git worktrees
- Automatic branch tracking
- Integrated with GitHub CLI

## Installation

```bash
pip install gitwork
```

## Usage

```bash
gitwork create <branch-name>
gitwork list
gitwork remove <worktree-path>
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
```

## License

MIT
