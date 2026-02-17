.PHONY: format format-py format-ts lint lint-py lint-ts generate-contracts

format: format-py format-ts

format-py:
	@echo "Formatting Python with black and ruff"
	black .
	ruff check . --fix

format-ts:
	@echo "Formatting TypeScript with Prettier"
	prettier --write "**/*.{ts,tsx,js,jsx,json,md}"

lint: lint-py lint-ts

lint-py:
	@echo "Linting Python with ruff"
	ruff check .

lint-ts:
	@echo "Linting TypeScript with ESLint"
	eslint . --ext .ts,.tsx,.js,.jsx


generate-contracts:
	@echo "Generating contract models (TypeScript + Python)"
	cd packages/contracts && ./scripts/generate-models.sh
