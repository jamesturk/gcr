
publish-pypi: #gen-completions
	uv run ruff check
	uv run ruff format --check
	rm -rf build/* dist/*
	uv build
	uv publish

# publish-docs:
# 	rm -rf site/*
# 	uv run zensical build
# 	uvx trifold publish

# preview:
# 	uv run zensical serve

# export _TYPER_COMPLETE_TEST_DISABLE_SHELL_DETECTION := "true"

# gen-completions:
# 	uv run circe --show-completion zsh > completions/completion.zsh
# 	uv run circe --show-completion bash > completions/completion.bash
# 	uv run circe --show-completion fish > completions/completion.fish
# 	uv run circe --show-completion powershell > completions/completion.powershell

