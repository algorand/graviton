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
	ls
	ls sandbox
	cd sandbox && docker-compose ps

integration-test:
	pytest -sv tests/integration_test.py


###### Mac Only ######

# assumes you have a symbolic link: sandbox -> /cloned/repo/algorand/sandbox
mac-sandbox-test:
	./sandbox/sandbox test

mac-blackbox-smoke: blackbox-smoke-prefix mac-sandbox-test

mac-blackbox: mac-blackbox-smoke integration-test


###### Github Actions Only ######

gh-sandbox-test:
	script -e -c "bash -x ./sandbox/sandbox test"

gh-blackbox-smoke: blackbox-smoke-prefix gh-sandbox-test

gh-blackbox: gh-blackbox-smoke integration-test

.PHONY: pip-publish pip-test unit-test gh-blackbox