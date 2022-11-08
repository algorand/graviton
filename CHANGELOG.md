<!-- markdownlint-disable MD024 -->
# Changelog

## `v0.5.0` (_aka_ 🐘)

### Added

* Ability to handle `dryrun_accounts` in dry run executions
* New assertable dryrun properties `budgetAdded` and `budgetConsumed` including the rewiring of `cost` to be computed as `budgetConsumed - budgetAdded`

### Fixed

* New `mypy` errors arising from stricter enforcement of setting of `None` to non-optional types

### Upgraded

* Various dependencies including `py-algorand-sdk>=1.16.1`

## `v0.4.1`

### Added

* Better Logos
* Badges for:
  * visitor count
  * "powered by Algorand"
* New `THANKS.md`

### Removed

* Original logo including _ALT_ link to graviton journal article in the following tag: `<img width="345" alt="http://cds.cern.ch/record/2315186/files/scoap3-fulltext.pdf" src="https://user-images.githubusercontent.com/291133/160721859-21a3560a-0a82-4249-aa54-5ede4c60f8d2.png">`

## `v0.4.0` (_aka_ 🐕)

### Added

* ABI Contract / Router / Execution functionality

### Fixed

* A bug that made all app calls run as if during creation
* Addressed [Issue #5](https://github.com/algorand/graviton/issues/5): Better assertion message for invariant predicates of 2 variables

### Upgraded

* Minimum python is bumped up to 3.9 (previously 3.8)

## `v0.3.0` (_aka_ 🐈)

### Added

* `mypy`
* Jupyter Notebooks
* Allow handling of Transaction Params in Logic Sig and App Dry-Runs

## `v0.2.0` (_aka_ 🐗)

### Added

* ABI Functionality (types only)

## `v0.1.2`

### Fixed

* Misleading error message in the case of an erroring dry run response

## `v0.1.1`

### Added

* Semantic versioning

## 🦙 (Alpaca)

### Added

* Basic functionality

## Just For Fun - Animal Emoji Lexicographical Order (AELO)

1. 🦙 (Alpaca) == `v0.1.0`
2. 🐗 (Boar) == `v0.2.0`
3. 🐈 (Cat) == `v0.3.0`
4. 🐕 (Dog) == `v0.4.0`
5. 🐘 (Elephant) == `v0.5.0`
6. 🐸 (Frog) == `v0.6.0`
... etc ...

## Tagging Cheatsheet

* create an annotated tag:
  * `git tag -as 🦙 -m "productionize graviton" && git push origin 🦙`
* get tag details:
  * `git show 🦙`
