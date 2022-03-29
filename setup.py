#!/usr/bin/env python3

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="graviton",
    version="0.0.1",
    author="Algorand",
    author_email="pypiservice@algorand.com",
    description="verify your TEAL program by experiment and observation",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/algorand/graviton",
    packages=setuptools.find_packages(),
    install_requires=["py-algorand-sdk", "tabulate==0.8.9"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
)
