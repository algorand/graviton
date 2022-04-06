from itertools import product

from pathlib import Path


from graviton.blackbox import (
    # DryRunEncoder as Encoder,
    DryRunExecutor as Executor,
    DryRunProperty as DRProp,
    DryRunInspector as DRR,
    # ExecutionMode,
    # mode_has_property,
)
from graviton.invariant import Invariant

from tests.clients import get_algod

TESTS_DIR = Path.cwd() / "tests"


def test_factorizer_game():
    path = TESTS_DIR / "teal"
    filebase = "lsig_factorizer_game_1_5_7"
    tealpath = path / f"{filebase}.teal"
    with open(tealpath, "r") as f:
        teal = f.read()

    inputs = list(product(range(20), range(20)))

    algod = get_algod()

    dryrun_results = Executor.dryrun_logicsig_on_sequence(algod, teal, inputs)

    csvpath = path / f"{filebase}.csv"
    with open(csvpath, "w") as f:
        f.write(DRR.csv_report(inputs, dryrun_results))

    last_message_invariant = Invariant(
        lambda args: "PASS" if set(args) == {5, 7} else "REJECT",
        name="final message REJECT exactly for args not {5, 7}",
    )
    last_message_invariant.validates(DRProp.lastMessage, inputs, dryrun_results)
