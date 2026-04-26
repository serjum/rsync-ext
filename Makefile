PYTHON ?= python3

.PHONY: help version install-local uninstall-local bump-patch bump-minor bump-major build-deb tag-release release-patch release-minor release-major release

help:
	@printf '%s\n' \
		'make version         Show current project version' \
		'make install-local   Install the app locally for the current user' \
		'make uninstall-local Remove the local install for the current user' \
		'make bump-patch      Increase patch version' \
		'make bump-minor      Increase minor version' \
		'make bump-major      Increase major version' \
		'make build-deb       Build the Debian package' \
		'make tag-release     Create git tag for current version' \
		'make release         Prompt for patch/minor/major/current, then build and tag' \
		'make release-patch   Bump patch, build deb, create tag' \
		'make release-minor   Bump minor, build deb, create tag' \
		'make release-major   Bump major, build deb, create tag'

version:
	@$(PYTHON) -c 'import tomllib; from pathlib import Path; data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8")); print(data["project"]["version"])'

install-local:
	@./scripts/install-local.sh

uninstall-local:
	@./scripts/uninstall-local.sh

bump-patch:
	@$(PYTHON) scripts/bump_version.py patch

bump-minor:
	@$(PYTHON) scripts/bump_version.py minor

bump-major:
	@$(PYTHON) scripts/bump_version.py major

build-deb:
	@./scripts/build-deb.sh

tag-release:
	@test -z "$$(git status --porcelain)" || { echo "Git working tree must be clean."; exit 1; }
	@version="$$( $(PYTHON) -c 'import tomllib; from pathlib import Path; data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8")); print(data["project"]["version"])' )"; \
	tag="v$$version"; \
	if git rev-parse "$$tag" >/dev/null 2>&1; then \
		echo "Tag $$tag already exists."; \
		exit 1; \
	fi; \
	git tag -a "$$tag" -m "Release $$tag"; \
	printf 'Created tag %s\n' "$$tag"; \
	printf 'Push it with: git push origin %s\n' "$$tag"

release:
	@./scripts/prepare_release.sh

release-patch:
	@RELEASE_TYPE=patch ./scripts/prepare_release.sh

release-minor:
	@RELEASE_TYPE=minor ./scripts/prepare_release.sh

release-major:
	@RELEASE_TYPE=major ./scripts/prepare_release.sh
