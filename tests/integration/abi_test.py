"""
Note on test-case generation for this file (as of 5/18/2022):

* test cases for `test_unit_abi_strategy_get_random()` and `test_roundtrip_abi_strategy()` depend
    on a fixtures directory
* the fixtures directory is defined by the constant ROUNDTRIP (currently this is ./tests/teal/roundtrip )
* all the files with name ending in ".teal" are considered
* such files are expected to have a name of the form "*_arc-4-abi-type-string_<dynamic-int>.teal" where the last
    token "_<dynamic-length>" is optional
* the tests are generated using `pytest` in the
    [pyteal repo](https://github.com/algorand/pyteal/blob/c9c01d744e76158dc6a03c79a694352ff1d6707b/tests/integration/abi_roundtrip_test.py)
* in that repo, run the command `pytest tests/integration/abi_roundtrip_test.py::test_pure_compilation`
* then copy the contents of the generated directory "./tests/integration/generated/roundtrip/" into the ROUNDTRIP directory
"""

import inspect
from itertools import product
from pathlib import Path
import pytest
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from algosdk import abi
from algosdk.transaction import OnComplete

from graviton.abi_strategy import RandomABIStrategy, RandomABIStrategyHalfSized
from graviton.ace import ABIContractExecutor
from graviton.blackbox import DryRunExecutor as DRE, DryRunEncoder
from graviton.inspector import DryRunProperty as DRProp
from graviton.invariant import Invariant
from graviton.models import ExecutionMode

from tests.clients import get_algod

ROUNDTRIP = Path.cwd() / "tests" / "teal" / "roundtrip"

DYNAMIC_ARRAY_SUM_TEAL = """#pragma version 6
txna ApplicationArgs 1      // x = abi.DynamicArray(abi.Uint64TypeSpec())
store 0                     // 0: x
load 0                      // [x]
callsub abisum_0
store 1
byte 0x151F7C75
load 1
itob
concat
log
int 1
return

// abi_sum
abisum_0:                   // [x]
store 2                     // 2: x
int 0                       // [0]
store 3                     // 3: 0
int 0                       // [0]
store 4                     // 4: 0
abisum_0_l1:                // []
load 4
load 2
int 0                       // [0, x, 0]
extract_uint16              // [0, len(x)]
store 6                     // 6: len(x)
load 6                      // [0, len(x)]
<                           // [1]
bz abisum_0_l3              // [0]
load 2                      // ... looks promising ...
int 8
load 4
*
int 2
+
extract_uint64
store 5
load 3
load 5
+
store 3
load 4
int 1
+
store 4
b abisum_0_l1
abisum_0_l3:                // []
load 3                      // [0]
retsub
"""


def test_dynamic_array_sum():
    algod = get_algod()
    args = ([1, 2, 3, 4, 5],)
    inspector = DRE(
        algod,
        ExecutionMode.Application,
        DYNAMIC_ARRAY_SUM_TEAL,
        abi_method_signature="abi_sum(uint64[])uint64",
    ).run_one(args)
    # with default config:
    assert inspector.abi_type
    assert inspector.suppress_abi is False
    assert inspector.has_abi_prefix is True

    print(inspector.last_log())
    assert inspector.last_log() == 15, inspector.report(args, "last log messed up")
    assert inspector.stack_top() == 1, inspector.report(args, "stack top messed up")

    inspector.config(suppress_abi=False, has_abi_prefix=True)
    assert inspector.abi_type
    assert inspector.suppress_abi is False
    assert inspector.has_abi_prefix is True

    assert inspector.last_log() == 15, inspector.report(args, "last log messed up")
    assert inspector.stack_top() == 1, inspector.report(args, "stack top messed up")

    inspector.config(suppress_abi=True)
    assert inspector.abi_type
    assert inspector.suppress_abi is True
    assert inspector.has_abi_prefix is True

    assert inspector.last_log() == "151f7c75000000000000000f", inspector.report(
        args, "last log messed up"
    )
    assert inspector.stack_top() == 1, inspector.report(args, "stack top messed up")


def process_filename(filename):
    abi_info = filename.split("/")[-1].split(".")[0].split("_")[2:]

    length = None
    if len(abi_info) > 1:
        abi_str, length = abi_info
        length = int(length[1:-1])
    else:
        abi_str = abi_info[0]

    abi_instance = abi.ABIType.from_string(abi_str)
    abi_strat = RandomABIStrategy(abi_instance, length)
    abi_sig = f"foo({abi_str})({abi_str},{abi_str},{abi_str})"
    return abi_str, length, abi_instance, abi_strat, abi_sig


def get_roundtrip_teals():
    return list(ROUNDTRIP.glob("*.teal"))


@pytest.mark.parametrize("roundtrip_app", get_roundtrip_teals())
def test_unit_abi_strategy_get_random(roundtrip_app):
    filename = str(roundtrip_app)

    abi_str, length, abi_instance, abi_strat, _ = process_filename(filename)
    rand = abi_strat.get()
    encoded = DryRunEncoder.encode_args([rand], abi_types=[abi_instance])
    decoded = abi_instance.decode(encoded[0])  # type: ignore
    assert decoded == rand

    print(
        f"""
roundtrip_app = {roundtrip_app}
abi_str = {abi_str}
length = {length}
abi_instance = {abi_instance}
rand = {rand}
encoded = {encoded[0]}
decoded = {decoded}
"""
    )


GAI_ISSUE_2050 = "https://github.com/algorand/go-algorand-internal/issues/2050"

BAD_TEALS = {
    "()": GAI_ISSUE_2050,
}


@pytest.mark.parametrize("roundtrip_app", get_roundtrip_teals())
def test_roundtrip_abi_strategy(roundtrip_app):
    filename = str(roundtrip_app)
    abi_str, _, abi_instance, abi_strat, method_sig = process_filename(filename)

    if abi_str in BAD_TEALS:
        print(
            f"Skipping encoding roundtrip test of '{abi_str}' because of {BAD_TEALS[abi_str]}"
        )
        return

    rand = abi_strat.get()

    algod = get_algod()
    args = (rand,)

    with open(filename) as f:
        roundtrip_teal = f.read()

    inspector = DRE(
        algod,
        ExecutionMode.Application,
        roundtrip_teal,
        abi_method_signature=method_sig,
        omit_method_selector=True,
    ).run_one(args)

    cost = inspector.cost()
    passed = inspector.passed()
    original, mut, mut_mut = inspector.last_log()

    print(
        f"""
roundtrip_app = {roundtrip_app}
cost = {cost}
abi_str = {abi_str}
abi_instance = {abi_instance}
rand = {rand}
original = {original}
mut = {mut}
mut_mut = {mut_mut}
"""
    )

    last_rows = 2

    assert passed == (cost <= 700), inspector.report(
        args, f"passed={passed} contradicted cost={cost}", last_steps=last_rows
    )
    assert rand == original, inspector.report(
        args, "rand v. original", last_steps=last_rows
    )
    assert original == mut_mut, inspector.report(
        args, "original v. mut_mut", last_steps=last_rows
    )

    expected_mut = abi_strat.mutate_for_roundtrip(rand)
    assert expected_mut == mut, inspector.report(
        args, "expected_mut v. mut", last_steps=last_rows
    )


# ---- ABI Router Dry Run Testing - SETUP ---- #

ROUTER = Path.cwd() / "tests" / "teal" / "router"
NUM_ROUTER_DRYRUNS = 7


QUESTIONABLE_CONTRACT = None
with open(ROUTER / "questionable.json") as f:
    QUESTIONABLE_CONTRACT = f.read()

QUESTIONABLE_TEAL = None
with open(ROUTER / "questionable.teal") as f:
    QUESTIONABLE_TEAL = f.read()

QUESTIONABLE_CLEAR_TEAL = None
with open(ROUTER / "questionable_clear.teal") as f:
    QUESTIONABLE_CLEAR_TEAL = f.read()

YACC_TEAL = None
with open(ROUTER / "yacc.teal") as f:
    YACC_TEAL = f.read()

YACC_CLEAR_TEAL = None
with open(ROUTER / "yacc_clear.teal") as f:
    YACC_CLEAR_TEAL = f.read()

QUESTIONABLE_ACE = ABIContractExecutor(
    QUESTIONABLE_TEAL,
    QUESTIONABLE_CONTRACT,
    argument_strategy=RandomABIStrategyHalfSized,
    dry_runs=NUM_ROUTER_DRYRUNS,
    handle_selector=True,
)

QUESTIONABLE_CLEAR_ACE = ABIContractExecutor(
    QUESTIONABLE_CLEAR_TEAL,
    QUESTIONABLE_CONTRACT,  # weird, but the methods in the clear program do belong to the contract
    argument_strategy=RandomABIStrategyHalfSized,
    dry_runs=NUM_ROUTER_DRYRUNS,
    handle_selector=True,
)

YACC_ACE = ABIContractExecutor(
    YACC_TEAL,
    QUESTIONABLE_CONTRACT,  # same JSON contract as QUESTIONABLE
    argument_strategy=RandomABIStrategyHalfSized,
    dry_runs=NUM_ROUTER_DRYRUNS,
    handle_selector=True,
)

YACC_CLEAR_ACE = ABIContractExecutor(
    YACC_CLEAR_TEAL,
    QUESTIONABLE_CONTRACT,
    argument_strategy=RandomABIStrategyHalfSized,
    dry_runs=NUM_ROUTER_DRYRUNS,
    handle_selector=True,
)


# LEGEND FOR TEST CASES (*_CASES and *_CLEAR_CASES):
#
# * @0 - method: str | None
#   method name when `str` or bare app call when `None`
#
# * @1 - call_types:  ...tuple[bool, OncComplete] | None
#   [(is_app_create, `OnComplete`), ...] contexts to test (`None` is short-hand for `[(False, OnComplete.NoOpOC)]`)
#
# * @2 - invariants: dict[DRProp, Any]
#   these are being asserted after being processed into actual Invariant's
#
QUESTIONABLE_CASES: List[
    Tuple[Optional[str], Optional[List[Tuple[bool, OnComplete]]], Dict[DRProp, Any]]
] = [
    (
        "add",
        None,
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] + args[2]},
    ),
    (
        "sub",
        None,
        {
            DRProp.passed: lambda args: args[1] >= args[2],
            DRProp.lastLog: (
                lambda args, actual: True
                if args[1] < args[2]
                else actual == args[1] - args[2]
            ),
        },
    ),
    (
        "mul",
        None,
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] * args[2]},
    ),
    (
        "div",
        None,
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] // args[2]},
    ),
    (
        "mod",
        None,
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] % args[2]},
    ),
    (
        "all_laid_to_args",
        None,
        {DRProp.passed: True, DRProp.lastLog: lambda args: sum(args[1:])},
    ),
    (
        "empty_return_subroutine",
        [
            (False, OnComplete.NoOpOC),
            (False, OnComplete.OptInOC),
            (True, OnComplete.OptInOC),
        ],
        {
            DRProp.passed: True,
            DRProp.lastLog: DryRunEncoder.hex(
                "appear in both approval and clear state"
            ),
        },
    ),
    (
        "log_1",
        [(False, OnComplete.NoOpOC), (False, OnComplete.OptInOC)],
        {DRProp.passed: True, DRProp.lastLog: 1},
    ),
    (
        "log_creation",
        [(True, OnComplete.NoOpOC)],
        {DRProp.passed: True, DRProp.lastLog: "logging creation"},
    ),
    (
        "approve_if_odd",  # this should only appear in the clear-state program
        [],
        {
            DRProp.passed: True,
            DRProp.lastLog: "THIS MAKES ABSOLUTELY NO SENSE ... SHOULD NEVER GET HERE!!!",
        },
    ),
    (
        None,
        [(False, OnComplete.OptInOC)],
        {DRProp.passed: True, DRProp.lastLog: DryRunEncoder.hex("optin call")},
    ),
]

# strip out the bare calls for YACC ~ "yetAnotherContractConstructedFromRouter":
YACC_CASES = [c for c in QUESTIONABLE_CASES if c[0]]

QUESTIONABLE_CLEAR_CASES: List[
    Tuple[Optional[str], Optional[List[Tuple[bool, OnComplete]]], Dict[DRProp, Any]]
] = [
    (
        "add",
        [],  # shouldn't appear in PyTEAL generated clear state program
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] + args[2]},
    ),
    (
        "sub",
        [],  # shouldn't appear in PyTEAL generated clear state program
        {
            DRProp.passed: lambda args: args[1] >= args[2],
            DRProp.lastLog: lambda args, actual: True
            if args[1] < args[2]
            else actual == args[1] - args[2],
        },
    ),
    (
        "mul",
        [],  # shouldn't appear in PyTEAL generated clear state program
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] * args[2]},
    ),
    (
        "div",
        [],  # shouldn't appear in PyTEAL generated clear state program
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] // args[2]},
    ),
    (
        "mod",
        [],  # shouldn't appear in PyTEAL generated clear state program
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] % args[2]},
    ),
    (
        "all_laid_to_args",
        [],  # shouldn't appear in PyTEAL generated clear state program
        {DRProp.passed: True, DRProp.lastLog: lambda args: sum(args[1:])},
    ),
    (
        "empty_return_subroutine",
        [
            (False, OnComplete.ClearStateOC),
        ],
        {
            DRProp.passed: True,
            DRProp.lastLog: DryRunEncoder.hex(
                "appear in both approval and clear state"
            ),
        },
    ),
    (
        "log_1",
        [(False, OnComplete.ClearStateOC)],
        {DRProp.passed: True, DRProp.lastLog: 1},
    ),
    (
        "log_creation",
        [],  # shouldn't appear in PyTEAL generated clear state program
        {DRProp.passed: True, DRProp.lastLog: "logging creation"},
    ),
    (
        "approve_if_odd",
        [(False, OnComplete.ClearStateOC)],
        {
            DRProp.passed: lambda args: bool(args[1] % 2),
        },
    ),
    (
        None,
        [(False, OnComplete.ClearStateOC)],
        {DRProp.passed: True, DRProp.lastLog: None},
    ),
]

# the YACC clear program accepts no bare calls!
# strip out the bare calls for YACC ~ "yetAnotherContractConstructedFromRouter":
YACC_CLEAR_CASES = [c for c in QUESTIONABLE_CLEAR_CASES if c[0]]


def method_or_barecall_positive_test_runner(ace, method, call_types, invariants):
    """
    Test the _positive_ version of a case. In other words, ensure that for the given:
        * method or bare call
        * OnComplete value
        * number of arguments
    that the app call succeeds according to the provided _invariants success definition_
    """
    algod = get_algod()

    if call_types is None:
        call_types = [(False, OnComplete.NoOpOC)]

    if not call_types:
        return

    def msg():
        return f"""
TEST CASE:
test_function={inspect.stack()[2][3]}
method={method}
is_app_create={is_app_create}
on_complete={on_complete!r}
dr_prop={dr_property}
invariant={invariant}"""

    predicates = Invariant.as_invariants(invariants)
    for is_app_create, on_complete in call_types:
        inspectors = ace.dry_run_on_sequence(
            algod,
            method=method,
            is_app_create=is_app_create,
            on_complete=on_complete,
        )
        for dr_property, invariant in predicates.items():
            invariant.validates(dr_property, inspectors, msg=msg())


# cf. https://death.andgravity.com/f-re for an explanation of verbose regex'es
EXPECTED_ERR_PATTERN = r"""
    assert\ failed                              # pyteal generated assert's ok
|   err\ opcode                                 # pyteal generated err's ok
|   invalid\ ApplicationArgs\ index             # failing because an app arg wasn't provided
|   extraction\ end\ [0-9]+\ is\ beyond\ length # failing because couldn't extract from jammed in tuple
"""

NEGATIVE_INVARIANTS = Invariant.as_invariants(
    {
        DRProp.rejected: True,
        DRProp.error: True,
        DRProp.errorMessage: lambda _, actual: (
            bool(re.search(EXPECTED_ERR_PATTERN, actual, re.VERBOSE))
        ),
    }
)


def method_or_barecall_negative_test_runner(
    ace, method, call_types, is_clear_state_program
):
    """
    Test the _negative_ version of a case. In other words, ensure that for the given:
        * method or bare call
        * OnComplete value
        * number of arguments
    explore the space _OUTSIDE_ of each constraint and assert that the app call FAILS!!!
    """
    algod = get_algod()

    if call_types is None:
        call_types = [(False, OnComplete.NoOpOC)]

    # iac_n_oc --> (is_app_create, on_complete)
    call_types_negation = [
        iac_n_oc
        for iac_n_oc in product((True, False), OnComplete)
        if iac_n_oc not in call_types
    ]
    good_inputs = ace.generate_inputs(method)

    is_app_create = on_complete = None

    def dry_runner(**kwargs):
        inputs = kwargs.get("inputs")
        assert inputs

        validation = kwargs.get("validation", True)

        return ace.dry_run_on_sequence(
            algod,
            method=method,
            is_app_create=is_app_create,
            on_complete=on_complete,
            inputs=inputs,
            validation=validation,
        )

    def msg():
        return f"""
TEST CASE:
test_function={inspect.stack()[1][3]}
is_clear_state_program={is_clear_state_program}
scenario={scenario}
method={method}
is_app_create={is_app_create}
on_complete={on_complete!r}
dr_prop={dr_prop}
invariant={invariant}"""

    if not is_clear_state_program:
        scenario = "I. explore all UNEXPECTED (is_app_create, on_complete) combos"
        for is_app_create, on_complete in call_types_negation:
            inspectors = dry_runner(inputs=good_inputs)
            for dr_prop, invariant in NEGATIVE_INVARIANTS.items():
                invariant.validates(dr_prop, inspectors, msg=msg())

    # II. explore changing method selector arg[0] by edit distance 1
    if good_inputs and good_inputs[0]:

        def factory(action):
            def selector_mod(args):
                args = args[:]
                selector = args[0]
                idx = random.randint(0, 4)
                prefix, suffix = selector[:idx], selector[idx:]
                if action == "insert":
                    selector = prefix + random.randbytes(1) + suffix
                elif action == "delete":
                    selector = (prefix[:-1] + suffix) if prefix else (suffix[:-1])
                else:  # "replace"
                    assert (
                        action == "replace"
                    ), f"expected action=replace but got [{action}]"
                    idx = random.randint(0, 3)
                    selector = (
                        selector[:idx]
                        + bytes([(selector[idx] + 1) % 256])
                        + selector[idx + 1 :]
                    )
                return (selector,) + args[1:]

            return selector_mod

        selectors_inserted = map(factory("insert"), good_inputs)
        selectors_deleted = map(factory("delete"), good_inputs)
        selectors_modded = map(factory("replace"), good_inputs)
    else:
        selectors_inserted = selectors_deleted = selectors_modded = None

    scenario = "II(a). inserting an extra random byte into method selector"
    if selectors_inserted:
        inspectors = dry_runner(inputs=selectors_inserted, validation=False)
        for dr_prop, invariant in NEGATIVE_INVARIANTS.items():
            invariant.validates(dr_prop, inspectors, msg=msg())

    scenario = "II(b). removing a random byte from method selector"
    if selectors_deleted:
        inspectors = dry_runner(inputs=selectors_deleted, validation=False)
        for dr_prop, invariant in NEGATIVE_INVARIANTS.items():
            invariant.validates(dr_prop, inspectors, msg=msg())

    scenario = "II(c). replacing a random byte in method selector"
    if selectors_modded:
        inspectors = dry_runner(inputs=selectors_modded, validation=False)
        for dr_prop, invariant in NEGATIVE_INVARIANTS.items():
            invariant.validates(dr_prop, inspectors, msg=msg())

    # III. explore changing the number of args over the 'good' call_types
    # (extra args testing is omitted as this is prevented by SDK's cf. https://github.com/algorand/algorand-sdk-testing/issues/190)
    if good_inputs and good_inputs[0]:
        missing_arg = [args[:-1] for args in good_inputs]
        if not missing_arg[0]:
            # skip this, as this becomes a bare app call case which is tested elsewhere
            return

        for is_app_create, on_complete in call_types:
            scenario = "III. removing the final argument"
            inspectors = dry_runner(inputs=missing_arg, validation=False)
            for dr_prop, invariant in NEGATIVE_INVARIANTS.items():
                invariant.validates(dr_prop, inspectors, msg=msg())


# ---- ABI Router Dry Run Testing - TESTS ---- #

# ## QUESTIONABLE ## #


@pytest.mark.parametrize("method, call_types, invariants", QUESTIONABLE_CASES)
def test_questionable_approval_method_or_barecall_positive(
    method, call_types, invariants
):
    method_or_barecall_positive_test_runner(
        QUESTIONABLE_ACE, method, call_types, invariants
    )


@pytest.mark.parametrize("method, call_types, invariants", QUESTIONABLE_CLEAR_CASES)
def test_questionable_clear_method_or_barecall_positive(method, call_types, invariants):
    method_or_barecall_positive_test_runner(
        QUESTIONABLE_CLEAR_ACE, method, call_types, invariants
    )


@pytest.mark.parametrize("method, call_types, _", QUESTIONABLE_CASES)
def test_questionable_approval_program_method_or_barecall_negative(
    method, call_types, _
):
    method_or_barecall_negative_test_runner(
        QUESTIONABLE_ACE, method, call_types, is_clear_state_program=False
    )


@pytest.mark.parametrize("method, call_types, _", QUESTIONABLE_CLEAR_CASES)
def test_questionable_clear_program_method_or_barecall_negative(method, call_types, _):
    method_or_barecall_negative_test_runner(
        QUESTIONABLE_ACE, method, call_types, is_clear_state_program=True
    )


# ## YACC (QUESTIONABLE Copy Pasta 🍝) ## #


@pytest.mark.parametrize("method, call_types, invariants", YACC_CASES)
def test_yacc_approval_method_or_barecall_positive(method, call_types, invariants):
    method_or_barecall_positive_test_runner(YACC_ACE, method, call_types, invariants)


@pytest.mark.parametrize("method, call_types, invariants", YACC_CLEAR_CASES)
def test_yacc_clear_method_or_barecall_positive(method, call_types, invariants):
    method_or_barecall_positive_test_runner(
        YACC_CLEAR_ACE, method, call_types, invariants
    )


@pytest.mark.parametrize("method, call_types, _", YACC_CASES)
def test_yacc_approval_program_method_or_barecall_negative(method, call_types, _):
    method_or_barecall_negative_test_runner(
        YACC_ACE, method, call_types, is_clear_state_program=False
    )


@pytest.mark.parametrize("method, call_types, _", YACC_CLEAR_CASES)
def test_yacc_clear_program_method_or_barecall_negative(method, call_types, _):
    method_or_barecall_negative_test_runner(
        YACC_ACE, method, call_types, is_clear_state_program=True
    )
