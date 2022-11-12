from copy import deepcopy
import pytest


from graviton.blackbox import DryRunProperty as DRProp, DryRunExecutor as DRExecutor
from graviton.invariant import Invariant, PredicateKind as IQ

# from graviton.models import ExecutionMode

from tests.clients import get_algod

square_teal = """#pragma version 7
txna ApplicationArgs 0
method "square(uint64)uint64"
==
assert
txna ApplicationArgs 1
btoi
callsub square_0
store 1
load 1
itob
byte 0x151f7c75
swap
concat
log
int 1
return

// square
square_0:
store 0
load 0
pushint 2 // 2
exp
retsub"""

square_plus_1_teal = """#pragma version 7
txna ApplicationArgs 0
method "square(uint64)uint64"
==
assert
txna ApplicationArgs 1
btoi
callsub square_0
store 1
load 1
itob
byte 0x151f7c75
swap
concat
log
int 1
return

// square
square_0:
store 0
load 0
pushint 2 // 2
exp
int 1
+
retsub"""


square_byref_teal = """#pragma version 7
txna ApplicationArgs 0
method "square_byref(uint64)uint64"
==
assert
txna ApplicationArgs 1
btoi
store 2
pushint 2 // 2
callsub squarebyref_0
// pushint 1337 // 1337 - TODO expose this for counter example
load 2
itob
byte 0x151f7c75
swap
concat
log
int 1
return

// square_byref
squarebyref_0:
store 0
load 0
load 0
loads
load 0
loads
*
stores
retsub"""

square = (square_teal, "square(uint64)uint64")
square_byref = (square_byref_teal, "square_byref(uint64)uint64")
square_p1 = (square_plus_1_teal, "square(uint64)uint64")
ten = [(i,) for i in range(10)]
identity_predicates = {
    DRProp.lastLog: IQ.IdenticalPair,
    DRProp.status: IQ.IdenticalPair,
    DRProp.error: IQ.IdenticalPair,
    DRProp.lastMessage: IQ.IdenticalPair,
}


COPACETIC = [
    (square, square, ten, identity_predicates),
    (square, square_byref, ten, identity_predicates),
    (square_byref, square, ten, identity_predicates),
    (square_byref, square_byref, ten, identity_predicates),
]


@pytest.mark.parametrize("teal_method1, teal_method2, inputs, predicates", COPACETIC)
def test_identical_functions(teal_method1, teal_method2, inputs, predicates):
    algod = get_algod()
    inspectors1, inspectors2 = DRExecutor.dryrun_app_pair_on_sequence(
        algod, teal_method1, teal_method2, inputs
    )
    Invariant.full_validation(
        predicates, inspectors=inspectors1, identities=inspectors2
    )


def test_non_idenical():
    algod = get_algod()
    square_inspectores, square_p1_inspectors = DRExecutor.dryrun_app_pair_on_sequence(
        algod, square, square_p1, ten
    )

    square_predicates = {
        DRProp.lastLog: lambda args: args[1] ** 2,
        DRProp.status: "PASS",
        DRProp.error: False,
        DRProp.lastMessage: "PASS",
    }
    Invariant.full_validation(
        square_predicates,
        inspectors=square_inspectores,
    )

    square_p1_predicates = deepcopy(square_predicates)
    square_p1_predicates[DRProp.lastLog] = lambda args: 1 + square_predicates[
        DRProp.lastLog
    ](args)
    Invariant.full_validation(
        square_p1_predicates,
        inspectors=square_p1_inspectors,
    )

    with pytest.raises(AssertionError) as ae:
        Invariant.full_validation(
            identity_predicates,
            inspectors=square_inspectores,
            identities=square_p1_inspectors,
        )

    assert (
        "Invariant of PredicateKind.IdenticalPair for 'DryRunProperty.lastLog' failed for for args (b'}\\\\R\\xfa', 0): (actual, expected) = (0, 1)"
        in str(ae.value)
    )
