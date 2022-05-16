from pathlib import Path
import pytest

from algosdk import abi

from graviton.blackbox import DryRunExecutor, DryRunEncoder, DryRunInspector
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
    return length, abi_str, abi_instance, abi_strat


def get_roundtrip_teals():
    return list(ROUNDTRIP.glob("*.teal"))


@pytest.mark.parametrize("roundtrip_app", get_roundtrip_teals())
def test_abi_strategy_get_random(roundtrip_app):
    filename = str(roundtrip_app)

    length, abi_str, abi_instance, abi_strat = process_filename(filename)
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
encoded = {encoded}
decoded = {decoded}
"""
    )
