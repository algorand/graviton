# Graviton - Testing TEAL via Dry Runs

## [Tutorial](./graviton/README.md)

## Local Installation

The following instructions assume that you have `make` available in your local environment. In Mac OS and Linux this is most likely already available and in Windows one way to install is with [chocolatey](https://chocolatey.org/) and the command `choco install make`.

To install all dependencies:

```sh
make pip-notebooks
```

## Running Blackbox Integration Tests against a Sandbox

### Prereq - Install and Symbolically Link to the Sandbox

If you would like to use the [Makefile](./Makefile) without modificationm and with full functionality, you should create a symbolic link to  [the algorand sandbox repo](https://github.com/algorand/sandbox) as described here. There are many ways to accomplish this. Assuming you have cloned ***the sandbox*** into the path  `/path/to/algorand/sandbox/` and that you've `cd`'ed into the cloned `graviton` directory you would want to create a symbolic link as follows:

#### linux / Mac OS

```sh
ln -s /path/to/algorand/sandbox/ sandbox
```

#### Windows 10+

```sh
mklink sandbox \path\to\algorand\sandbox
```

### Start and Test the Sandbox

If your sandbox isn't already running, you can start the sandbox with a command such as

```sh
make local-sandbox-up SANDBOX_ENV=dev
```

To test that the sandbox is running properly, use the following:

```sh
make local-sandbox-test
```

### Run the Integration Tests

```sh
make integration-test
```

## Running and Testing Jupyter Notebook

To run the notebook `notebooks/quadratic_factoring_game.ipynb` for example:

```sh
make local-notebook NOTEBOOK=notebooks/quadratic_factoring_game.ipynb
```

To run all the automated jupyter nontebook tests:

```sh
notebooks-test
```

## Ensuring that all is Copacetic Before Pushing to Github

To test in your local environment that everything is looking good before pushing to Github, it is recommended that you run `make pre-commit-check`

If you would like to simulate the github actions locally, you'll need to install [nektos act](https://github.com/nektos/act/wiki/Installation). On Mac OS, if you already have [Docker](https://docs.docker.com/desktop/mac/install/) installed you can use `brew install act`, while
on Linux and Windows, you should follow the installation instructions in the nextos repo link above.

Once `act` is available you can simulate all the github actions integration tests with:

```sh
make local-gh-simulate
```

