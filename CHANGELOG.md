<!-- markdownlint-disable MD024 -->
# Changelog

## `v0.9.0` (_aka_ 🐐)

### Bugs fixed

Changes in `go-algorand`'s handling of dry run errors broke the methods `error()` and `error_message()` of `DryRunInspector`.  This is fixed in [#49](https://github.com/algorand/graviton/pull/49)

### Breaking changes

* `class ABIContractExecutor` renamed to `ABICallStrategy` and moved from `graviton/blackbox.py` to `graviton/abi_strategy.py`. Some of the methods have been renamed as well ([#49](https://github.com/algorand/graviton/pull/49))

### Added
* `class Simulation` in `graviton/sim.py` unifies the ability to run an argument strategy and check that invariants hold using its `run_and_assert()` method ([#49](https://github.com/algorand/graviton/pull/49))
* `class DryRunTransactionParameters` has a new method `update_fields()` ([#49](https://github.com/algorand/graviton/pull/49))

## `v0.8.0` (_aka_ 🦛)

### Breaking changes

In [#48](https://github.com/algorand/graviton/pull/48), the following classes were pulled out of `graviton/blackbox.py` and into a new file `graviton/inspector.py`
* `TealVal`
* `DryRunResults` (renamed from `BlackboxResults`)
* `DryRunInspector`

In [#44](https://github.com/algorand/graviton/pull/44):
* `DryRunExecutor` has been refactored. All the class methods `dryrun_*` have been removed in favor of the instance methods `run_one()` and `run_sequence()`. In particular, it is now required to instantiate a `DryRunExecutor` object  before calling a dry run executing method.
* `DryRunInspector` no longer accepts `args` as a second parameter and uses `self.args` instead.
* Migration path to the above: it is recommended that calls be re-written to use the new API. If you find that this causes too much friction, please open an issue.
### Added
* Adding `budget_added` and `budget_consumed` to `DryRunInspector.csv_row()`

### Addressed
* [#45](https://github.com/algorand/graviton/pull/45): addresses [#38](https://github.com/algorand/graviton/issues/38) and [#40](https://github.com/algorand/graviton/issues/40)
* [#48](https://github.com/algorand/graviton/pull/48): addresses [#14](https://github.com/algorand/graviton/issues/14) and [#29](https://github.com/algorand/graviton/issues/29)

## `v0.7.1`

### Breaking changes

* Upgrade to `py-algorand-sdk` v2 ([#46](https://github.com/algorand/graviton/pull/46))

## `v0.7.0` (_aka_ 🦒)

### Breaking changes

In [#42](https://github.com/algorand/graviton/pull/42):

* Inside `graviton/blackbox.py`: Removing the parameters `abi_argument_types` and `abi_return_type` from dry run execution methods, in favor of the unified `abi_method_signature` parameter. Also adding `omit_method_selector` and `validation` parameters to allow running non-ARC-4 compliant teal code that use ABI types.
* Deleting orphaned code mostly brought over from original py-algorand-sdk code:
  * Entire file: `graviton/deprecated_dryrun.py`
  * Entire file: `graviton/deprecated_dryrun_mixin.py`
  * Entire file: `tests/integration/dryrun_mixin_docs_test.py`
  * The following functions and methods in `graviton/dryrun.py`:
    * `_fail()`
    * `assert_pass()`
    * `assert_reject()`
    * `assert_status()`
    * `assert_global_state_contains()`
    * `assert_local_state_contains()`
    * `DryRunHelper._guess()`
    * `DryRunHelper.format_stack()`
    * `DryRunHelper.find_delta_value()`
    * `DryRunHelper.save_dryrun_request()`
  * Recommended actions in case you are currently using the above:
    * Consider opening an issue alerting us of the impact
    * The original code is mostly available [in py-algorand v1.20.2](https://github.com/algorand/py-algorand-sdk/blob/v1.20.2/algosdk/testing/dryrun.py)
* Deleting method `Invariant.inputs_and_invariants()`
  * Recommended migration path: It is recommended that inputs and invariants be accessed directly from the
  dictionary that contains them (e.g. [this example](https://github.com/algorand/graviton/blob/7aed927405d8c7fc27ee34cfd05caa001b89ea36/tests/integration/blackbox_test.py#L463)) or that
  `Invariant.full_validation()` be employed instead (e.g. [this example](https://github.com/algorand/graviton/blob/d84fc612a0ad9ec23a6ec14a167fa9f2c898bd2e/tests/integration/identical_test.py#L123)).

## `v0.6.0` (_aka_ 🐸)

### Added

* `class PredicateKind` introduced to strengthen typing of predicates and invariants
* `PredicateKind.IdenticalPair`: allow asserting identical behavior of teal programs without specifying behavior details

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
