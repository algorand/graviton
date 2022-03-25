pip-publish:
	pip install -r requirements.txt
	pip install -e .

pip-test:
	pip install -r requirements.txt
	pip install .

unit-test:
	pytest tests/unit_test.py

blackbox-smoke-test:
	echo "hello blackbox!"
	pwd
	ls
	ls sandbox
	cd sandbox && bash -x ./sandbox test
	pwd

integration-test:
	pytest tests/integration_test.py

blackbox: blackbox-smoke-test integration-test

.PHONY: pip-publish pip-test unit-test blackbox