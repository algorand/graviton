# Github Actions

env-up:
	bash -x .sandbox/sandbox up dev

env-down:
	.sandbox/sandbox down dev

# Build

pip:
	pip install -r requirements.txt
	pip install -e .


build-and-test:
	pytest tests/unit_test.py

blackbox:
	echo "hello blackbox!"
	pwd
	ls
	./sandbox test
	pytest tests/integration_test.py
