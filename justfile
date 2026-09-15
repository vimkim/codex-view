# Show available commands.
default:
    @just --list

# Install the user-level codex-view command from this checkout.
install:
    uv tool install --python "$(cat .python-version)" .

# Refresh the installed command from this checkout.
reinstall:
    uv tool install --reinstall --python "$(cat .python-version)" .

# Pull the current branch with fast-forward only, then refresh the installed command.
reinstall-after-update:
    git pull --ff-only
    just reinstall

# Install the locked development dependencies.
sync:
    uv sync --locked

# Run lint, formatting checks, and tests.
check:
    uv run --locked ruff check .
    uv run --locked ruff format --check .
    uv run --locked pytest -q

# Build the distributable package.
build:
    uv build
