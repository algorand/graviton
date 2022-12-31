import pytest
import re

teal = """#pragma version 6
arg 0
btoi
callsub square_0
return

// square
square_0:
store 0
load 0
pushint 2 // 2
exp
retsub"""


def test_step4():
    from graviton.blackbox import DryRunExecutor, ExecutionMode
    from tests.clients import get_algod

    algod = get_algod()
    x = 9
    args = (x,)
    inspector = DryRunExecutor(algod, ExecutionMode.Signature, teal).run_one(args)
    assert inspector.status() == "PASS"
    assert inspector.stack_top() == x**2

    print(inspector.stack_top())
    print(inspector.last_log())
    print(inspector.cost())
    print(inspector.status())
    print(inspector.final_scratch())
    print(inspector.error())
    print(inspector.max_stack_height())


def test_step5():
    from graviton.blackbox import DryRunExecutor, ExecutionMode
    from tests.clients import get_algod

    algod = get_algod()
    x = 2
    args = (x,)
    inspector = DryRunExecutor(algod, ExecutionMode.Signature, teal).run_one(args)

    # This one's ok
    expected, actual = "PASS", inspector.status()
    assert expected == actual, inspector.report(
        args, f"expected {expected} but got {actual}"
    )

    # This one's absurd! x^3 != x^2
    expected, actual = x**3, inspector.stack_top()

    # wrap for test purposes only
    with pytest.raises(AssertionError) as ae:
        assert expected == actual, inspector.report(
            args, f"expected {expected} but got {actual}"
        )
    expected = """AssertionError:
===============
<<<<<<<<<<<expected 8 but got 4>>>>>>>>>>>
===============
      App Trace:
   step |   PC# |   L# | Teal              | Scratch   | Stack
--------+-------+------+-------------------+-----------+----------------------
      1 |     1 |    1 | #pragma version 6 |           | []
      2 |     2 |    2 | arg_0             |           | [0x0000000000000002]
      3 |     3 |    3 | btoi              |           | [2]
      4 |     7 |    6 | label1:           |           | [2]
      5 |     9 |    7 | store 0           | 0->2      | []
      6 |    11 |    8 | load 0            |           | [2]
      7 |    13 |    9 | pushint 2         |           | [2, 2]
      8 |    14 |   10 | exp               |           | [4]
      9 |     6 |    4 | callsub label1    |           | [4]
     10 |    15 |   11 | retsub            |           | [4]
===============
MODE: ExecutionMode.Signature
TOTAL COST: None
===============
FINAL MESSAGE: PASS
===============
Messages: ['PASS']
Logs: []
===============
-----BlackBoxResult(steps_executed=10)-----
TOTAL STEPS: 10
FINAL STACK: [4]
FINAL STACK TOP: 4
MAX STACK HEIGHT: 2
FINAL SCRATCH: {0: 2}
SLOTS USED: [0]
FINAL AS ROW: {'steps': 10, ' top_of_stack': 4, 'max_stack_height': 2, 's@000': 2}
===============
Global Delta:
[]
===============
Local Delta:
[]
===============
TXN AS ROW: {' Run': 0, ' cost': None, ' last_log': '`None', ' final_message': 'PASS', ' Status': 'PASS', 'steps': 10, ' top_of_stack': 4, 'max_stack_height': 2, 's@000': 2, 'Arg_00': 2}
===============
<<<<<<<<<<<expected 8 but got 4>>>>>>>>>>>
===============
assert 8 == 4
"""

    def remove_whitespace(s):
        return re.sub(r"\s+", "", s)

    assert remove_whitespace(expected) == remove_whitespace(ae.exconly())


def test_step6_and_7():
    from graviton.blackbox import DryRunExecutor, DryRunInspector, ExecutionMode
    from tests.clients import get_algod

    algod = get_algod()
    inputs = [(x,) for x in range(16)]
    run_results = DryRunExecutor(algod, ExecutionMode.Signature, teal).run_sequence(
        inputs
    )
    csv = DryRunInspector.csv_report(inputs, run_results)
    print(csv)

    for i, inspector in enumerate(run_results):
        args = inputs[i]
        x = args[0]
        inspector.stack_top() == x**2
        inspector.max_stack_height() == 2
        inspector.status() == ("REJECT" if x == 0 else "PASS")
        inspector.final_scratch() == ({} if x == 0 else {0: x})


def test_step8():
    from graviton.blackbox import DryRunExecutor, ExecutionMode
    from tests.clients import get_algod

    algod = get_algod()
    inputs = [(x,) for x in range(101)]
    dryrun_results = DryRunExecutor(algod, ExecutionMode.Signature, teal).run_sequence(
        inputs
    )
    for i, inspector in enumerate(dryrun_results):
        args = inputs[i]
        x = args[0]
        assert inspector.stack_top() == x**2
        assert inspector.max_stack_height() == 2
        assert inspector.status() == ("REJECT" if x == 0 else "PASS")
        assert inspector.final_scratch() == ({} if x == 0 else {0: x})


def test_step9():
    from graviton.blackbox import (
        DryRunExecutor,
        DryRunProperty as DRProp,
        ExecutionMode,
    )
    from graviton.invariant import Invariant
    from tests.clients import get_algod

    algod = get_algod()

    scenario = {
        "inputs": [(i,) for i in range(100)],
        "invariants": {
            DRProp.stackTop: lambda args: args[0] ** 2,
            DRProp.maxStackHeight: 2,
            DRProp.status: lambda args: "REJECT" if args[0] == 0 else "PASS",
            DRProp.finalScratch: lambda args: ({0: args[0]} if args[0] else {}),
        },
    }
    # Validate the scenario and dig out inputs/invariants:
    inputs = scenario["inputs"]
    invariants = Invariant.as_invariants(scenario["invariants"])
    assert inputs and isinstance(inputs, list)
    assert invariants and isinstance(invariants, dict)

    # Execute the dry runs and obtain sequence of DryRunInspectors:
    inspectors = DryRunExecutor(algod, ExecutionMode.Signature, teal).run_sequence(
        inputs
    )

    # Invariant assertions on sequence:
    for dr_property, invariant in invariants.items():
        invariant.validates(dr_property, inspectors)


@pytest.mark.parametrize("exercise", ["A", "B"])
def test_exercises(exercise):
    from graviton.blackbox import (
        DryRunExecutor,
        DryRunProperty as DRProp,
        ExecutionMode,
    )
    from graviton.invariant import Invariant
    from tests.clients import get_algod

    algod = get_algod()

    status_predicate = (
        ({(x,): "PASS" if x else "REJECT" for x in range(100)})
        if exercise == "A"
        else (lambda args, actual: "PASS" == actual if args[0] else True)
    )
    scenario = {
        "inputs": [(i,) for i in (2, 7, 13, 11)],
        "invariants": {
            DRProp.stackTop: {(2,): 4, (7,): 49, (13,): 169, (11,): 121},
            DRProp.maxStackHeight: 2,
            DRProp.status: status_predicate,
            DRProp.finalScratch: lambda args: ({0: args[0]} if args[0] else {}),
        },
    }
    # Validate the scenario and dig out inputs/invariants:
    inputs = scenario["inputs"]
    invariants = Invariant.as_invariants(scenario["invariants"])
    assert inputs and isinstance(inputs, list)
    assert invariants and isinstance(invariants, dict)

    # Execute the dry runs and obtain sequence of DryRunInspectors:
    inspectors = DryRunExecutor(algod, ExecutionMode.Signature, teal).run_sequence(
        inputs
    )

    # Invariant assertions on sequence:
    for dr_property, invariant in invariants.items():
        invariant.validates(dr_property, inspectors)
