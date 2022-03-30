####### Universal ######

pip:
	pip install --upgrade pip
	pip install -e .

pip-test: pip
	pip install -e.[test]

black:
	black .


unit-test:
	pytest -sv tests/unit

blackbox-smoke-prefix:
	echo "hello blackbox!"
	pwd
	ls -l
	ls -l sandbox
	cd sandbox && docker-compose ps

integration-test:
	pytest -sv tests/integration


###### Local Only ######

# assumes installations of pipx, build and tox via:
# `pip install pipx; pipx install build; pipx install tox`
local-project-build:
	pyproject-build

# assumes a symbolic link: sandbox -> /cloned/repo/algorand/sandbox
local-sandbox-test:
	./sandbox/sandbox test

local-blackbox-smoke: blackbox-smoke-prefix local-sandbox-test

local-blackbox: local-blackbox-smoke integration-test

# assumes act is installed, e.g. via `brew install act`:
local-gh-simulate:
	act

###### Github Actions Only ######

gh-sandbox-test:
	# relax exit code condition because indexer returns 500 when last-round = 0
	script -e -c "bash -x ./sandbox/sandbox test" || echo "finished ./sandbox test"

gh-blackbox-smoke: blackbox-smoke-prefix gh-sandbox-test

gh-blackbox: gh-blackbox-smoke integration-test
