pip-publish:
	pip install -r requirements.txt
	pip install -e .

pip-test:
	pip install -r requirements.txt
	pip install .

unit-test:
	pytest tests/unit_test.py

blackbox:
	echo "hello blackbox!"
	pwd
	ls
	./sandbox test
	pytest tests/integration_test.py

.PHONY: pip-publish pip-test unit-test blackbox