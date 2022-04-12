from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="graviton",
    version="0.0.1",
    url="https://github.com/algorand/graviton",
    description="verify your TEAL program by experiment and observation",
    long_description=long_description,
    author="Algorand",
    author_email="pypiservice@algorand.com",
    python_requires=">=3.8",
    install_requires=["py-algorand-sdk", "tabulate==0.8.9"],
    extras_require={
        "development": [
            "black==22.3.0",
            "flake8==4.0.1",
            "hypothesis==6.41.0",
            "mypy==0.942",
            "pytest==7.1.1",
            "pytest-xdist==2.5.0",
            "types-tabulate==0.8.6",
        ]
        "notebooks": [
            "jupyter-client==7.2.2",
            "jupyter-core==4.9.2",
            "nbformat==5.3.0",
            "pandas==1.4.2",
            "plotly==5.7.0",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    package_data={"graviton": ["py.typed"]},
    packages=find_packages(),
)
