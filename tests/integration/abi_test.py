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


from pathlib import Path
import pytest

from algosdk import abi

from graviton.blackbox import DryRunExecutor, DryRunEncoder
from graviton.abi_strategy import ABIStrategy

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
    args = ("ignored", [1, 2, 3, 4, 5])
    abi_arg_types = (None, abi.ArrayDynamicType(abi.UintType(64)))
    abi_out_type = abi.UintType(64)
    inspector = DryRunExecutor.dryrun_app(
        algod, DYNAMIC_ARRAY_SUM_TEAL, args, abi_arg_types, abi_out_type
    )
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
    abi_strat = ABIStrategy(abi_instance, length)
    return abi_str, length, abi_instance, abi_strat


def get_roundtrip_teals():
    return list(ROUNDTRIP.glob("*.teal"))


@pytest.mark.parametrize("roundtrip_app", get_roundtrip_teals())
def test_unit_abi_strategy_get_random(roundtrip_app):
    filename = str(roundtrip_app)

    abi_str, length, abi_instance, abi_strat = process_filename(filename)
    rand = abi_strat.get_random()
    encoded = DryRunEncoder.encode_args([rand], abi_types=[abi_instance])
    decoded = abi_instance.decode(encoded[0])
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
    abi_str, _, abi_instance, abi_strat = process_filename(filename)

    if abi_str in BAD_TEALS:
        print(
            f"Skipping encoding roundtrip test of '{abi_str}' because of {BAD_TEALS[abi_str]}"
        )
        return

    rand = abi_strat.get_random()

    algod = get_algod()
    args = (rand,)
    abi_arg_types = (abi_instance,)
    abi_out_type = abi.TupleType([abi_instance] * 3)

    with open(filename) as f:
        roundtrip_teal = f.read()

    inspector = DryRunExecutor.dryrun_app(
        algod, roundtrip_teal, args, abi_arg_types, abi_out_type
    )

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
