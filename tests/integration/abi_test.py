from algosdk import abi

from graviton.blackbox import DryRunExecutor

from tests.clients import get_algod

dyanmic_array_sum_teal = """#pragma version 6
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
        algod, dyanmic_array_sum_teal, args, abi_arg_types, abi_out_type
    )
    inspector.config(suppress_abi=False, has_abi_prefix=True, force_abi=False)
    assert inspector.last_log() == 15
    assert inspector.stack_top() == 1
