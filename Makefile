####### Universal ######

pip-publish:
	pip install -r requirements.txt
	pip install -e .

pip-test:
	pip install -r requirements.txt
	pip install .

unit-test:
	pytest tests/unit_test.py

blackbox-smoke-prefix:
	echo "hello blackbox!"
	pwd
	ls -l
	ls -l sandbox
	cd sandbox && docker-compose ps

integration-test:
	pytest -sv tests/integration_test.py


###### Mac Only ######

# assumes installations of pipx, build and tox via:
# `pip install pipx; pipx install build; pipx install tox`
mac-project-build:
	pyproject-build

# assumes a symbolic link: sandbox -> /cloned/repo/algorand/sandbox
mac-sandbox-test:
	./sandbox/sandbox test

mac-blackbox-smoke: blackbox-smoke-prefix mac-sandbox-test

mac-blackbox: mac-blackbox-smoke integration-test

# assumes you've installed act via `brew install act`:
mac-gh-simulate:
	act


###### Github Actions Only ######

gh-sandbox-test:
	# allow exit code 2 as indexer returns 500 when last-round = 0
	script -e -c "bash -x ./sandbox/sandbox test" || echo "finished ./sandbox test"

gh-blackbox-smoke: blackbox-smoke-prefix gh-sandbox-test

gh-blackbox: gh-blackbox-smoke integration-test

.PHONY: pip-publish pip-test unit-test gh-blackbox