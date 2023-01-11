####### Universal ######

pip:
	pip install -e .

pip-development: pip
	pip install -e.[development]

pip-notebooks: pip-development
	pip install -e.[notebooks]

black:
	black --check .

flake8:
	flake8 graviton tests

mypy:
	mypy .

lint: black flake8 mypy

unit-test:
	pytest -sv tests/unit

build-and-test: pip-development lint unit-test

blackbox-smoke-prefix:
	echo "hello blackbox!"
	pwd
	ls -l
	ls -l sandbox
	cd sandbox && docker-compose ps

NUM_PROCS = auto
VERBOSITY = -sv
integration-test:
	pytest -n $(NUM_PROCS) --durations=10 $(VERBOSITY) tests/integration

notebooks-test:
	pytest --nbmake -n $(NUM_PROCS) notebooks

all-tests: lint unit-test integration-test notebooks-test

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

NOTEBOOK = notebooks/quadratic_factoring_game.ipynb
# assumes already ran `make pip-notebooks`
local-notebook:
	 jupyter retro $(NOTEBOOK)

# assumes act is installed, e.g. via `brew install act`:
local-gh-simulate:
	act

###### Github Actions Only ######

gh-sandbox-test:
	# relax exit code condition because indexer returns 500 when last-round = 0
	script -e -c "bash -x ./sandbox/sandbox test" || echo "finished ./sandbox test"

gh-blackbox-smoke: blackbox-smoke-prefix gh-sandbox-test

gh-blackbox: integration-test notebooks-test
