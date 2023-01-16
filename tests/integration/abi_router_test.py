from dataclasses import dataclass
import inspect
from itertools import product
from pathlib import Path
import random
import re
from typing import Any, Dict, List, Tuple

import pytest

from algosdk.transaction import OnComplete

from graviton.abi_strategy import RandomABIStrategyHalfSized
from graviton.abi_args_strategy import ABIArgsStrategy
from graviton.blackbox import DryRunEncoder, DryRunTransactionParams as TxParams
from graviton.inspector import DryRunProperty as DRProp
from graviton.invariant import Invariant
from graviton.models import ExecutionMode
from graviton.sim import Simulation

from tests.clients import get_algod

# ---- ABI Router Dry Run Testing - SETUP ---- #

ROUTER = Path.cwd() / "tests" / "teal" / "router"
NUM_ROUTER_DRYRUNS = 7


@dataclass
class MethodRunner:
    name: str
    approval: bool  # False indicates a clear state program
    teal: str
    contract: str
    method: str

    def __repr__(self) -> str:
        return f"MethodRunner[{self.name}].{self.method}"


def get_fixture(fix):
    with open(ROUTER / fix) as f:
        return f.read()


(
    CONTRACT,
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


def qa_runner(m):
    return MethodRunner("questionable_approval", True, QUESTIONABLE_TEAL, CONTRACT, m)


def qc_runner(m):
    return MethodRunner(
        "questionable_clear", False, QUESTIONABLE_CLEAR_TEAL, CONTRACT, m
    )


TYPICAL_IAC_OC = (False, OnComplete.NoOpOC)

# LEGEND FOR TEST CASES (*_CASES and *_CLEAR_CASES):
#
# * @0 - approval method_runner: MethodRunner(name: str, approval: bool, teal: str, contract: str, method: str)
#   method == `None` indicates bare app call
#
# * @1 - approval_call_types: list[tuple[bool, OncComplete]]
#   [(is_app_create, `OnComplete`), ...] contexts expected for approval program
#
# * @2 - clear method_runner: MethodRunner(name: str, approval: bool, teal: str, contract: str, method: str)
#   method == `None` indicates bare app call
#
# * @3 - clear_call_types: list[tuple[bool, Oncomplete]]
#   [(is_app_create, `OnComplete`), ...] contexts expected for clear program
#
# * @4 - predicates: dict[DRProp, Any]
#   these are being asserted after being processed into Invariant's
#
QUESTIONABLE_CASES: List[
    Tuple[
        MethodRunner,
        List[Tuple[bool, OnComplete]],
        MethodRunner,
        List[Tuple[bool, OnComplete]],
        Dict[DRProp, Any],
    ]
] = [
    (
        qa_runner("add"),
        [TYPICAL_IAC_OC],
        qc_runner("add"),
        [],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] + args[2]},
    ),
    (
        qa_runner("sub"),
        [TYPICAL_IAC_OC],
        qc_runner("sub"),
        [],
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
        qa_runner("mul"),
        [TYPICAL_IAC_OC],
        qc_runner("mul"),
        [],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] * args[2]},
    ),
    (
        qa_runner("div"),
        [TYPICAL_IAC_OC],
        qc_runner("div"),
        [],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] // args[2]},
    ),
    (
        qa_runner("mod"),
        [TYPICAL_IAC_OC],
        qc_runner("mod"),
        [],
        {DRProp.passed: True, DRProp.lastLog: lambda args: args[1] % args[2]},
    ),
    (
        qa_runner("all_laid_to_args"),
        [TYPICAL_IAC_OC],
        qc_runner("all_laid_to_args"),
        [],
        {DRProp.passed: True, DRProp.lastLog: lambda args: sum(args[1:])},
    ),
    (
        qa_runner("empty_return_subroutine"),
        [
            (False, OnComplete.NoOpOC),
            (False, OnComplete.OptInOC),
            (True, OnComplete.OptInOC),
        ],
        qc_runner("empty_return_subroutine"),
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
        qa_runner("log_1"),
        [(False, OnComplete.NoOpOC), (False, OnComplete.OptInOC)],
        qc_runner("log_1"),
        [
            (False, OnComplete.ClearStateOC),
        ],
        {DRProp.passed: True, DRProp.lastLog: 1},
    ),
    (
        qa_runner("log_creation"),
        [(True, OnComplete.NoOpOC)],
        qc_runner("log_creation"),
        [],
        {DRProp.passed: True, DRProp.lastLog: "logging creation"},
    ),
    (
        qa_runner(
            "approve_if_odd"
        ),  # this should only appear in the clear-state program
        [],
        qc_runner("approve_if_odd"),
        [
            (False, OnComplete.ClearStateOC),
        ],
        {
            DRProp.passed: lambda args: args[1] % 2 == 1,
            DRProp.lastLog: None,
        },
    ),
    (
        qa_runner(None),
        [(False, OnComplete.OptInOC)],
        qc_runner(None),
        [
            (False, OnComplete.ClearStateOC),
        ],
        {
            DRProp.passed: True,
            DRProp.lastLog: lambda _, actual: actual
            in (None, DryRunEncoder.hex("optin call")),
        },
    ),
]


def make_yacc_runner(method, approval):
    return MethodRunner(
        f"yacc_{'approval' if approval else 'clear'}",
        approval,
        YACC_TEAL if approval else YACC_CLEAR_TEAL,
        CONTRACT,
        method,
    )


# strip out the bare calls for YACC ~ "yetAnotherContractConstructedFromRouter":
def yaccify(q_cases):
    return [
        (make_yacc_runner(method, True), c[1], make_yacc_runner(method, False), *c[3:])
        for c in q_cases
        if (method := c[0].method)
    ]


YACC_CASES = yaccify(QUESTIONABLE_CASES)

ALL_CASES = QUESTIONABLE_CASES + YACC_CASES


@pytest.mark.parametrize(
    "approval_runner, approval_call_types, clear_runner, clear_call_types, invariants",
    ALL_CASES,
)
def test_pos(
    approval_runner, approval_call_types, clear_runner, clear_call_types, invariants
):
    """
    Test the _positive_ version of a case. In other words, ensure that for the given:
        * method or bare call
        * OnComplete value
        * number of arguments
    that the app call succeeds according to the provided _invariants success definition_
    """

    def run_positive(is_approve, method_runner, call_types, invariants):
        ace = ABIArgsStrategy(
            method_runner.teal,
            method_runner.contract,
            RandomABIStrategyHalfSized,
            num_dryruns=NUM_ROUTER_DRYRUNS,
        )

        algod = get_algod()

        if not call_types:
            return

        method = method_runner.method
        sim = Simulation(
            algod,
            ExecutionMode.Application,
            method_runner.teal,
            invariants,
            abi_method_signature=ace.method_signature(method),
            omit_method_selector=False,
            validation=False,
        )

        def msg():
            return f"""
    TEST CASE [{method_runner}]({"APPROVAL" if is_approve else "CLEAR"}):
    test_function={inspect.stack()[2][3]}
    method={method}
    is_app_create={is_app_create}
    on_complete={on_complete!r}"""

        for is_app_create, on_complete in call_types:
            sim_result = sim.run_and_assert(
                ace.generate_inputs(method),
                txn_params=TxParams.for_app(
                    is_app_create=is_app_create,
                    on_complete=on_complete,
                ),
                msg=msg(),
            )
            assert sim_result.succeeded
            # inspectors = ace.run_sequence(
            #     algod,
            #     method=method,
            #     is_app_create=is_app_create,
            #     on_complete=on_complete,
            # )
            # TODO: the following is redundant and should be removed soon!
            Invariant.full_validation(
                invariants, sim_result.simulate_inspectors, msg=msg()
            )

    run_positive(True, approval_runner, approval_call_types, invariants)
    run_positive(False, clear_runner, clear_call_types, invariants)


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


@pytest.mark.parametrize(
    "approval_runner, approval_call_types, clear_runner, clear_call_types, _",
    ALL_CASES,
)
def test_neg(approval_runner, approval_call_types, clear_runner, clear_call_types, _):
    """
    Test the _negative_ version of a case. In other words, ensure that for the given:
        * method or bare call
        * OnComplete value
        * number of arguments
    explore the space _OUTSIDE_ of each constraint and assert that the app call FAILS!!!
    """

    def run_negative(is_approve, method_runner, call_types):
        ace = ABIArgsStrategy(
            method_runner.teal,
            method_runner.contract,
            RandomABIStrategyHalfSized,
            num_dryruns=NUM_ROUTER_DRYRUNS,
        )

        algod = get_algod()

        method = method_runner.method
        sim = Simulation(
            algod,
            ExecutionMode.Application,
            method_runner.teal,
            NEGATIVE_INVARIANTS,
            abi_method_signature=ace.method_signature(method),
            omit_method_selector=False,
            validation=False,
        )

        # iac_n_oc --> (is_app_create, on_complete)
        call_types_negation = [
            iac_n_oc
            for iac_n_oc in product((True, False), OnComplete)
            if iac_n_oc not in call_types
        ]
        good_inputs = ace.generate_inputs(method)

        def simulate_with_invariants_check(**kwargs):
            inputs = kwargs.get("inputs")
            app_create = kwargs.get("is_app_create")
            oc = kwargs.get("on_complete")
            assert inputs

            # validation = kwargs.get("validation", True)

            sim_result = sim.run_and_assert(
                inputs,
                txn_params=TxParams.for_app(
                    is_app_create=app_create,
                    on_complete=oc,
                ),
            )
            assert sim_result.succeeded

            return sim_result.simulate_inspectors
            # return ace.run_sequence(
            #     algod,
            #     method=method,
            #     is_app_create=app_create,
            #     on_complete=oc,
            #     inputs=inputs,
            #     validation=validation,
            # )

        is_approval = method_runner.approval

        is_app_create = on_complete = None

        def msg():
            return f"""
    TEST CASE [{method_runner}]({"APPROVAL" if is_approve else "CLEAR"}):
    test_function={inspect.stack()[2][3]}
    is_clear_state_program={not is_approval}
    scenario={scenario}
    method={method}
    is_app_create={is_app_create}
    on_complete={on_complete!r}"""

        if is_approval:
            scenario = "I. explore all UNEXPECTED (is_app_create, on_complete) combos"
            for is_app_create, on_complete in call_types_negation:
                inspectors = simulate_with_invariants_check(
                    inputs=good_inputs,
                    is_app_create=is_app_create,
                    on_complete=on_complete,
                )
                # TODO: the following is redundant and should be removed soon!
                Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

        is_app_create, on_complete = (
            call_types[0] if call_types else (False, OnComplete.NoOpOC)
        )

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

            selectors_inserted = list(map(factory("insert"), good_inputs))
            selectors_deleted = list(map(factory("delete"), good_inputs))
            selectors_modded = list(map(factory("replace"), good_inputs))
        else:
            selectors_inserted = selectors_deleted = selectors_modded = None

        scenario = "II(a). inserting an extra random byte into method selector"
        if selectors_inserted:
            inspectors = simulate_with_invariants_check(
                inputs=selectors_inserted,
                is_app_create=is_app_create,
                on_complete=on_complete,
            )
            # TODO: the following is redundant and should be removed soon!
            Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

        scenario = "II(b). removing a random byte from method selector"
        if selectors_deleted:
            inspectors = simulate_with_invariants_check(
                inputs=selectors_deleted,
                is_app_create=is_app_create,
                on_complete=on_complete,
            )
            # TODO: the following is redundant and should be removed soon!
            Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

        scenario = "II(c). replacing a random byte in method selector"
        if selectors_modded:
            inspectors = simulate_with_invariants_check(
                inputs=selectors_modded,
                is_app_create=is_app_create,
                on_complete=on_complete,
            )
            # TODO: the following is redundant and should be removed soon!
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
                inspectors = simulate_with_invariants_check(
                    inputs=missing_arg,
                    is_app_create=is_app_create,
                    on_complete=on_complete,
                )
                # TODO: the following is redundant and should be removed soon!
                Invariant.full_validation(NEGATIVE_INVARIANTS, inspectors, msg=msg())

    run_negative(True, approval_runner, approval_call_types)
    run_negative(False, clear_runner, clear_call_types)
