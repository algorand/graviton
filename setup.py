from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="graviton",
    version="0.8.0",
    url="https://github.com/algorand/graviton",
    description="verify your TEAL program by experiment and observation",
    long_description=long_description,
    author="Algorand",
    author_email="pypiservice@algorand.com",
    python_requires=">=3.9",
    install_requires=["py-algorand-sdk>=2.0.0,<3.0.0", "tabulate==0.9.0"],
    extras_require={
        "development": [
            "black==22.10.0",
            "flake8==5.0.4",
            "mypy==0.990",
            "pytest==7.2.0",
            "pytest-xdist==3.0.2",
            "types-tabulate==0.9.0.0",
        ],
        "notebooks": [
            "nbmake==1.3.0",
            "pandas==1.4.2",
            "plotly==5.7.0",
            "retrolab==0.3.20",
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
