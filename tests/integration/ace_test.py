import inspect
from itertools import product
from pathlib import Path
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import pytest

from algosdk.transaction import OnComplete

from graviton.abi_strategy import RandomABIStrategyHalfSized
from graviton.ace import ABIContractExecutor
from graviton.blackbox import DryRunEncoder
from graviton.inspector import DryRunProperty as DRProp
from graviton.invariant import Invariant

from tests.clients import get_algod

# ---- ABI Router Dry Run Testing - SETUP ---- #

ROUTER = Path.cwd() / "tests" / "teal" / "router"
NUM_ROUTER_DRYRUNS = 7


def get_fixture(fix):
    with open(ROUTER / fix) as f:
        return f.read()


(
    QUESTIONABLE_CONTRACT,
    QUESTIONABLE_TEAL,
    QUESTIONABLE_CLEAR_TEAL,
    YACC_TEAL,
    YACC_CLEAR_TEAL,
) = tuple(
    map(
        get_fixture,
        (
            "questionable.json",
            "questionable.teal",
            "questionable_clear.teal",
            "yacc.teal",
            "yacc_clear.teal",
        ),
    )
)


QUESTIONABLE_ACE = ABIContractExecutor(
    QUESTIONABLE_TEAL,
    QUESTIONABLE_CONTRACT,
    argument_strategy=RandomABIStrategyHalfSized,
    num_dryruns=NUM_ROUTER_DRYRUNS,
)

QUESTIONABLE_CLEAR_ACE = ABIContractExecutor(
    QUESTIONABLE_CLEAR_TEAL,
    QUESTIONABLE_CONTRACT,  # weird, but the methods in the clear program do belong to the contract
    argument_strategy=RandomABIStrategyHalfSized,
    num_dryruns=NUM_ROUTER_DRYRUNS,
)

YACC_ACE = ABIContractExecutor(
    YACC_TEAL,
    QUESTIONABLE_CONTRACT,  # same JSON contract as QUESTIONABLE
    argument_strategy=RandomABIStrategyHalfSized,
    num_dryruns=NUM_ROUTER_DRYRUNS,
)

YACC_CLEAR_ACE = ABIContractExecutor(
    YACC_CLEAR_TEAL,
    QUESTIONABLE_CONTRACT,
    argument_strategy=RandomABIStrategyHalfSized,
    num_dryruns=NUM_ROUTER_DRYRUNS,
)


TYPICAL_IAC_OC = (False, OnComplete.NoOpOC)

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
        [TYPICAL_IAC_OC],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] + args[2]},
    ),
    (
        "sub",
        [TYPICAL_IAC_OC],
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
        [TYPICAL_IAC_OC],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] * args[2]},
    ),
    (
        "div",
        [TYPICAL_IAC_OC],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] // args[2]},
    ),
    (
        "mod",
        [TYPICAL_IAC_OC],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] % args[2]},
    ),
    (
        "all_laid_to_args",
        [TYPICAL_IAC_OC],
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

    if not call_types:
        # TODO: silly hack to not actually test clear cases
        return

    def msg():
        return f"""
TEST CASE:
test_function={inspect.stack()[2][3]}
method={method}
is_app_create={is_app_create}
on_complete={on_complete!r}"""

    for is_app_create, on_complete in call_types:
        inspectors = ace.run_sequence(
            algod,
            method=method,
            is_app_create=is_app_create,
            on_complete=on_complete,
        )
        Invariant.full_validation(invariants, inspectors, msg=msg())


# cf. https://death.andgravity.com/f-re for an explanation of verbose regex'es
EXPECTED_ERR_PATTERN = r"""
    assert\ failed                              # pyteal generated assert's ok
|   err\ opcode                                 # pyteal generated err's ok
|   invalid\ ApplicationArgs\ index             # failing because an app arg wasn't provided
|   extraction\ end\ [0-9]+\ is\ beyond\ length # failing because couldn't extract from jammed in tuple
"""

NEGATIVE_INVARIANTS = {
    DRProp.rejected: True,
    DRProp.error: True,
    DRProp.errorMessage: lambda _, actual: (
        bool(re.search(EXPECTED_ERR_PATTERN, actual, re.VERBOSE))
    ),
}


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

    # iac_n_oc --> (is_app_create, on_complete)
    call_types_negation = [
        iac_n_oc
        for iac_n_oc in product((True, False), OnComplete)
        if iac_n_oc not in call_types
    ]
    good_inputs = ace.generate_inputs(method)

    is_app_create = on_complete = None

    def dryrun(**kwargs):
        inputs = kwargs.get("inputs")
        assert inputs

        validation = kwargs.get("validation", True)

        return ace.run_sequence(
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
on_complete={on_complete!r}"""

    if not is_clear_state_program:
        scenario = "I. explore all UNEXPECTED (is_app_create, on_complete) combos"
        for is_app_create, on_complete in call_types_negation:
            inspectors = dryrun(inputs=good_inputs)
            Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

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
        inspectors = dryrun(inputs=selectors_inserted, validation=False)
        Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

    scenario = "II(b). removing a random byte from method selector"
    if selectors_deleted:
        inspectors = dryrun(inputs=selectors_deleted, validation=False)
        Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

    scenario = "II(c). replacing a random byte in method selector"
    if selectors_modded:
        inspectors = dryrun(inputs=selectors_modded, validation=False)
        Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

    # III. explore changing the number of args over the 'good' call_types
    # (extra args testing is omitted as this is prevented by SDK's cf. https://github.com/algorand/algorand-sdk-testing/issues/190)
    if good_inputs and good_inputs[0]:
        missing_arg = [args[:-1] for args in good_inputs]
        if not missing_arg[0]:
            # skip this, as this becomes a bare app call case which is tested elsewhere
            return

        for is_app_create, on_complete in call_types:
            scenario = "III. removing the final argument"
            inspectors = dryrun(inputs=missing_arg, validation=False)
            Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())


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
