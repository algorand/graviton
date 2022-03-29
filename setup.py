from setuptools import setup, find_packages

setup(
    python_requires=">=3.8",
    install_requires=["py-algorand-sdk", "tabulate==0.8.9"],
    name="graviton",
    version="0.0.1",
    description="TBD",
    author="TBD",
    url="https://github.com/algorand/graviton",
    # py_modules=["blackbox"],
    packages=find_packages("blackbox/"),
)


#!/usr/bin/env python3

# import setuptools

# with open("README.md", "r") as fh:
#     long_description = fh.read()

# setuptools.setup(
#     name="graviton",
#     version="0.0.1",
#     author="Algorand",
#     author_email="pypiservice@algorand.com",
#     description="verify your TEAL program by experiment and observation",
#     long_description=long_description,
#     long_description_content_type="text/markdown",
#     url="https://github.com/algorand/graviton",
#     packages=setuptools.find_packages(),
#     # package_dir={"": "."},
#     install_requires=["py-algorand-sdk", "tabulate==0.8.9"],
#     classifiers=[
#         "Programming Language :: Python :: 3",
#         "License :: OSI Approved :: MIT License",
#         "Operating System :: OS Independent",
#     ],
#     package_data={"pyteal": ["*.pyi"]},
#     python_requires=">=3.8",
# )
