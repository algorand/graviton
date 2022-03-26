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

# assumes you've installed pipx, build and tox via:
# pip install pipx; pipx install build; pipx install tox
mac-project-build:
	pyproject-build

# assumes you have a symbolic link: sandbox -> /cloned/repo/algorand/sandbox
mac-sandbox-test:
	./sandbox/sandbox test

mac-blackbox-smoke: blackbox-smoke-prefix mac-sandbox-test

mac-blackbox: mac-blackbox-smoke integration-test

mac-publish: py

###### Github Actions Only ######

gh-sandbox-test:
	# expect exit code 2 on github and 0 on mac, as indexer is not present in the install but is on the typical sandbox
	script -e -c "bash -x ./sandbox/sandbox test"; if $? -eq 2 ]; then echo 0; else echo $?; fi

gh-blackbox-smoke: blackbox-smoke-prefix gh-sandbox-test

gh-blackbox: gh-blackbox-smoke integration-test

.PHONY: pip-publish pip-test unit-test gh-blackbox