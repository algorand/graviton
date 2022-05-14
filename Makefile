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

local-blackbox: integration-testq

NOTEBOOK = notebooks/quadratic_factoring_game.ipynb
# assumes already ran `make pip-notebooks`
local-notebook: 
	 jupyter retro $(NOTEBOOK)

# assumes act is installed, e.g. via `brew install act`:
local-gh-simulate:
	act

###### Github Actions Only ######

gh-blackbox: integration-test notebooks-test
