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
	pytest tests/blackbox_test.py

blackbox:
	echo "hello blackbox!"
