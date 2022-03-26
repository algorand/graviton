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
    from blackbox.blackbox import DryRunExecutor
    from tests.clients import get_algod

    algod = get_algod()
    x = 9
    args = (x,)
    inspector = DryRunExecutor.dryrun_logicsig(algod, teal, args)
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
    from blackbox.blackbox import DryRunExecutor
    from tests.clients import get_algod

    algod = get_algod()
    x = 2
    args = (x,)
    inspector = DryRunExecutor.dryrun_logicsig(algod, teal, args)

    # This one's ok
    expected, actual = "PASS", inspector.status()
    assert expected == actual, inspector.report(
        args, f"expected {expected} but got {actual}"
    )

    # This one's absurd! x^3 != x^2
    expected, actual = x**3, inspector.stack_top()
    assert expected == actual, inspector.report(
        args, f"expected {expected} but got {actual}"
    )


def test_step6():
    from blackbox.blackbox import DryRunExecutor, DryRunInspector
    from tests.clients import get_algod

    algod = get_algod()
    inputs = [(x,) for x in range(16)]
    run_results = DryRunExecutor.dryrun_logicsig_on_sequence(algod, teal, inputs)
    csv = DryRunInspector.csv_report(inputs, run_results)
    print(csv)
