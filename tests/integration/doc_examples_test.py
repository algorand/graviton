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
    dryrun_result = DryRunExecutor.dryrun_logicsig(algod, teal, args)
    assert dryrun_result.status() == "PASS"
    assert dryrun_result.stack_top() == x**2

    print(dryrun_result.stack_top())
    print(dryrun_result.last_log())
    print(dryrun_result.cost())
    print(dryrun_result.status())
    print(dryrun_result.final_scratch())
    print(dryrun_result.error())
    print(dryrun_result.max_stack_height())
