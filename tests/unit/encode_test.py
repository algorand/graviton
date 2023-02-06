import pytest
from typing import Optional
from unittest.mock import Mock

from json.decoder import JSONDecodeError

from algosdk.abi import ArrayDynamicType, BoolType, Contract, TupleType, UintType

from graviton.blackbox import DryRunEncoder

from graviton.abi_strategy import (
    ABIArgsMod,
    ABICallStrategy,
    RandomABIStrategy,
    RandomABIStrategyHalfSized,
)


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

    abi_types = [PyInt65, None, PyInt65, None, None]
    args = [[True, 42], 42, [False, 1339], "I am a string", b"I am bytes I am"]
    expected = [
        PyInt65.encode([True, 42]),
        (42).to_bytes(8, "big"),
        PyInt65.encode([False, 1339]),
        "I am a string",
        b"I am bytes I am",
    ]
    actual = encoder(args, abi_types=abi_types)
    assert expected == actual

    PyDynArr = ArrayDynamicType(UintType(64))
    abi_types = [PyDynArr, None, None]
    args = [[1, 3, 5, 7, 9], 42, "blah"]
    expected = [PyDynArr.encode([1, 3, 5, 7, 9]), (42).to_bytes(8, "big"), "blah"]
    actual = encoder(args, abi_types=abi_types)
    assert expected == actual

    with pytest.raises(AssertionError) as ae:
        encoder(args)

    assert (
        ae.value.args[0]
        == "problem encoding arg ([1, 3, 5, 7, 9]) at index (0): can't handle arg [[1, 3, 5, 7, 9]] of type <class 'list'>"
    )

    with pytest.raises(AssertionError) as ae:
        encoder(args, abi_types=[1, 2, 3, 4])

    assert (
        ae.value.args[0] == "mismatch between args (length=3) and abi_types (length=4)"
    )

    args = [["wrong", "types", "for", "dynamic", "int", "array"], "blah", "blah"]
    with pytest.raises(AssertionError) as ae:
        encoder(args, abi_types=[PyDynArr, None, None])

    assert (
        ae.value.args[0]
        == "problem encoding arg (['wrong', 'types', 'for', 'dynamic', 'int', 'array']) at index (0): can't handle arg [['wrong', 'types', 'for', 'dynamic', 'int', 'array']] of type <class 'list'> and abi-type uint64[]: value wrong is not a non-negative int or is too big to fit in size 64"
    )


def test_ABICallStrategy_init():
    contract = "very bad contract"
    argument_strategy = RandomABIStrategyHalfSized
    num_dryruns = Mock(int)
    handle_selector = Mock(bool)
    abi_args_mod: Optional[ABIArgsMod] = None

    # fail as the contract is garbage
    with pytest.raises(JSONDecodeError):
        ABICallStrategy(
            contract,
            argument_strategy,
            num_dryruns=num_dryruns,
            handle_selector=handle_selector,
            abi_args_mod=abi_args_mod,
        )

    # ok, let's give a real contract
    contract = '{"name":"ExampleContract","desc":"This is an example contract","networks":{"wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8=":{"appID":1234},"SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=":{"appID":5678}},"methods":[{"name":"add","args":[{"type":"uint32"},{"type":"uint32"}],"returns":{"type":"uint32"}}]}'
    amcs = ABICallStrategy(
        contract,
        argument_strategy,
        num_dryruns=num_dryruns,
        handle_selector=handle_selector,
        abi_args_mod=abi_args_mod,
    )

    assert (
        isinstance(amcs.contract, Contract)
        and "add" == amcs.contract.dictify()["methods"][0]["name"]
    )
    assert amcs.argument_strategy is argument_strategy
    assert amcs.num_dryruns == num_dryruns
    assert amcs.handle_selector is handle_selector
    assert amcs.abi_args_mod is abi_args_mod

    # what about defaults?
    amcs = ABICallStrategy(
        contract,
    )
    assert (
        isinstance(amcs.contract, Contract)
        and "add" == amcs.contract.dictify()["methods"][0]["name"]
    )
    assert amcs.argument_strategy is RandomABIStrategy
    assert amcs.num_dryruns == 1
    assert amcs.handle_selector is True
    assert amcs.abi_args_mod is None


def test_ABIMethoCallStrategy_method_etc():
    contract = '{"name":"ExampleContract","desc":"This is an example contract","networks":{"wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8=":{"appID":1234},"SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=":{"appID":5678}},"methods":[{"name":"add","args":[{"type":"uint32"},{"type":"uint32"}],"returns":{"type":"uint32"}}]}'
    argument_strategy = RandomABIStrategyHalfSized
    num_dryruns = Mock(int)
    handle_selector = Mock(bool)
    abi_args_mod: Optional[ABIArgsMod] = None

    amcs = ABICallStrategy(
        contract,
        argument_strategy,
        num_dryruns=num_dryruns,
        handle_selector=handle_selector,
        abi_args_mod=abi_args_mod,
    )

    # but we'll fail because the method is garbage so doesn't exist in the contract
    method = "doesn't exist"
    with pytest.raises(KeyError) as ke:
        amcs.abi_method(method)
    assert f"found 0 methods for {method}" in str(ke.value)

    # finally pass with an actual contract method:
    method = "add"
    abi_method = amcs.abi_method(method)
    assert abi_method.name == method

    # bare app call:
    with pytest.raises(AssertionError) as ae:
        amcs.abi_method(None)
    assert "cannot get abi.Method for bare app call" == str(ae.value)

    with pytest.raises(AssertionError) as ae:
        amcs.method_selector(None)
    assert "cannot get method_selector for bare app call" == str(ae.value)

    # falsey:
    assert not amcs.method_signature(None)
    assert not amcs.argument_types(None)
    assert not amcs.num_args(None)
