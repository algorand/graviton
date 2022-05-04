from algosdk.abi import TupleType, BoolType, UintType, ArrayDynamicType
from pandas import UInt32Dtype, UInt64Dtype
import pytest

from graviton.blackbox import DryRunEncoder


def test_encode_arg():
    encoder = DryRunEncoder._encode_arg

    idx = 17

    expected = arg = b"I am bytes I am"
    assert expected == encoder(arg, idx, None)

    expected = arg = "I am a string I am"
    assert expected == encoder(arg, idx, None)

    arg = 42
    expected = arg.to_bytes(8, "big")
    assert expected == encoder(arg, idx, None)

    arg = 42.1337
    with pytest.raises(AssertionError) as ae:
        encoder(arg, idx, None)

    assert (
        ae.value.args[0]
        == "problem encoding arg (42.1337) at index (17): can't handle arg [42.1337] of type <class 'float'>"
    )


def test_encode_abi():
    encoder = DryRunEncoder.encode_args

    PyInt65 = TupleType(arg_types=[BoolType(), UintType(64)])

    args = [[True, 42], 42, [False, 1339], "I am a string", b"I am bytes I am"]
    expected = [
        PyInt65.encode([True, 42]),
        (42).to_bytes(8, "big"),
        PyInt65.encode([False, 1339]),
        "I am a string",
        b"I am bytes I am",
    ]
    actual = encoder(args, abi_types=[PyInt65, None, PyInt65, None, None])
    assert expected == actual

    PyDynArr = ArrayDynamicType(UintType(64))
    args = [[1, 3, 5, 7, 9], 42, "blah"]
    expected = [PyDynArr.encode([1, 3, 5, 7, 9]), (42).to_bytes(8, "big"), "blah"]
    actual = encoder(args, abi_types=[PyDynArr, None, None])
    assert expected == actual
