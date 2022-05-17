from itertools import product
from pathlib import Path

import pytest


from graviton.blackbox import (
    DryRunExecutor as Executor,
    DryRunInspector as Inspector,
)

from tests.clients import get_algod

ALGOD = get_algod()
TESTS_DIR = Path.cwd() / "tests"


def test_factorizer_game_report():
    filebase = "lsig_factorizer_game_1_5_7"
    path = TESTS_DIR / "teal"
    tealpath = path / f"{filebase}.teal"
    with open(tealpath, "r") as f:
        teal = f.read()

    inputs = list(product(range(20), range(20)))

    algod = get_algod()

    dryrun_results = Executor.dryrun_logicsig_on_sequence(algod, teal, inputs)

    csvpath = path / f"{filebase}.csv"
    with open(csvpath, "w") as f:
        f.write(Inspector.csv_report(inputs, dryrun_results))


def test_logic_sig():
    source = """
arg 0
btoi
int 0x31
==
"""
    insp_no_args = Executor.dryrun_logicsig(ALGOD, source, [])
    assert "cannot load arg[0] of 0" in insp_no_args.error_message()
    assert insp_no_args.rejected()

    # providing the string arg "1" results is encoded to 0x31, and hence eval passes:
    insp_args_1_2 = Executor.dryrun_logicsig(ALGOD, source, ["1", "2"])
    assert insp_args_1_2.passed()


lsig_file = TESTS_DIR / "teal" / "lsig_factorizer_game_1_5_7.teal"
with open(lsig_file, "r") as f:
    FACTORIZER_TEAL = f.read()


def poly_4(x):
    return abs(x**2 - 12 * x + 35)


def expected_prize_before_dupe_constraint(p, q):
    return 1_000_000 * max(10 - (sum(map(poly_4, (p, q))) + 1) // 2, 0)


def payment_amount(p, q):
    return 0 if p == q else expected_prize_before_dupe_constraint(p, q)


@pytest.mark.parametrize("p, q", product(range(20), range(20)))
def test_factorizer_game_3_stateless(p, q):
    args = (p, q)
    inspector = Executor.dryrun_logicsig(ALGOD, FACTORIZER_TEAL, args)
    slots = inspector.final_scratch()
    assert slots.get(3, 0) == expected_prize_before_dupe_constraint(
        p, q
    ), inspector.report(args)


@pytest.mark.parametrize("p, q", product(range(20), range(20)))
def test_factorizer_game_4_payout(p, q):
    args = (p, q)
    eprize = expected_prize_before_dupe_constraint(p, q)
    inspector = Executor.dryrun_logicsig(ALGOD, FACTORIZER_TEAL, args, amt=eprize)
    assert inspector.final_scratch().get(3, 0) == eprize, inspector.report(
        args, f"final scratch slot #3 {p, q}"
    )
    actual_prize = payment_amount(p, q)
    assert inspector.passed() == bool(actual_prize), inspector.report(
        args, f"passed {p, q}"
    )


def test_factorizer_report_with_pymnt():
    filebase = "lsig_factorizer_game_1_5_7_V4"
    path = TESTS_DIR / "teal"
    tealpath = path / f"{filebase}.teal"
    with open(tealpath, "r") as f:
        teal = f.read()

    inputs = list(product(range(20), range(20)))
    amts = list(map(lambda args: payment_amount(*args), inputs))
    algod = get_algod()

    dryrun_results, txns = [], []
    for args, amt in zip(inputs, amts):
        txn = {"amt": amt}
        txns.append(txn)
        dryrun_results.append(Executor.dryrun_logicsig(algod, teal, args, **txn))

    csvpath = path / f"{filebase}.csv"
    with open(csvpath, "w") as f:
        f.write(Inspector.csv_report(inputs, dryrun_results, txns=txns))
