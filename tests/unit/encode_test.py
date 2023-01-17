import pytest
from typing import Optional
from unittest.mock import Mock

from json.decoder import JSONDecodeError

from algosdk.abi import ArrayDynamicType, BoolType, Contract, TupleType, UintType
from algosdk.error import ABIEncodingError
from algosdk.v2client.algod import AlgodClient

from graviton.abi_strategy import (
    ABIArgsMod,
    ABIMethodCallStrategy,
    RandomABIStrategy,
    RandomABIStrategyHalfSized,
)
from graviton.blackbox import DryRunEncoder, DryRunExecutor
from graviton.models import ExecutionMode


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


NONSENSE = "not a valid signature"


@pytest.mark.parametrize("mode", ExecutionMode)
@pytest.mark.parametrize(
    "abi_method_signature",
    [None, "zero()void", "one(uint64)void", "oneOne(uint64)bool", NONSENSE],
)
@pytest.mark.parametrize("omit_method_selector", [False, True])
@pytest.mark.parametrize("validation", [False, True])
def test_executor_init(mode, abi_method_signature, omit_method_selector, validation):
    if abi_method_signature == NONSENSE:
        with pytest.raises(ABIEncodingError) as abiee:
            DryRunExecutor(
                algod := Mock(AlgodClient),
                mode,
                teal := "fake teal",
                abi_method_signature=abi_method_signature,
                omit_method_selector=omit_method_selector,
                validation=validation,
            )

        assert (
            f"ABI method string has mismatched parentheses: {abi_method_signature}"
            == str(abiee.value)
        )
        return None

    sigless = abi_method_signature is None
    void = (not sigless) and abi_method_signature.endswith("void")
    dre = DryRunExecutor(
        algod := Mock(AlgodClient),
        mode,
        teal := "fake teal",
        abi_method_signature=abi_method_signature,
        omit_method_selector=omit_method_selector,
        validation=validation,
    )

    # simple WYSIWYG members:
    assert dre.algod == algod
    assert dre.mode == mode
    assert dre.program == teal
    assert dre.abi_method_signature == abi_method_signature
    assert dre.omit_method_selector == omit_method_selector
    assert dre.validation == validation

    assert dre.is_app == (mode == ExecutionMode.Application)

    # assert nullity first:
    assert (dre.abi_argument_types is None) == sigless
    assert (dre.abi_return_type is None) == sigless or void
    assert (dre.method is None) == sigless
    assert (dre.selector is None) == sigless

    # deeper assertions:
    if not sigless:
        assert dre.abi_argument_types == [a.type for a in dre.method.args]  # type: ignore
        if not void:
            assert dre.abi_return_type == dre.method.returns.type  # type: ignore
        assert dre.method.get_signature() == abi_method_signature  # type: ignore
        assert dre.selector == dre.method.get_selector()  # type: ignore

    return dre


@pytest.mark.parametrize("mode", ExecutionMode)
@pytest.mark.parametrize(
    "abi_method_signature",
    [None, "zero()void", "one(uint64)void", "oneOne(uint64)bool"],
)
@pytest.mark.parametrize("omit_method_selector", [False, True])
@pytest.mark.parametrize("validation", [False, True])
@pytest.mark.parametrize(
    "args", [tuple(), ("one",), (2,), ("three", 3), tuple([20] * 20)]
)  # _run
def test_executor_prep(
    mode, abi_method_signature, omit_method_selector, validation, args
):
    dre = test_executor_init(
        mode, abi_method_signature, omit_method_selector, validation
    )
    assert dre

    args_below_max_num = len(args) <= 16
    aats_out_is_none = dre.abi_argument_types is None

    if aats_out_is_none:
        assert dre.method is None
        assert dre.selector is None
        assert dre.abi_method_signature is None  # so will skip _abi_adapter() call
        assert dre.abi_argument_types is None  # so will encode args without

        if not args_below_max_num:
            with pytest.raises(AssertionError) as ae:
                dre._executor_prep(args)

            assert (
                "for non-ABI app calls, there is no specification for encoding more than"
                in str(ae.value)
            )
            return

        encoded_args = DryRunEncoder.encode_args(args)
        args_out, encoded_args_out = dre._executor_prep(args)
        assert args_out == args
        assert encoded_args_out == encoded_args
        return

    assert dre.method
    assert dre.selector
    assert dre.abi_method_signature
    assert isinstance(dre.abi_argument_types, list)

    argnum_same = len(args) == len(dre.abi_argument_types)
    argnum_one_more = len(args) == len(dre.abi_argument_types) + 1
    arg0_is_selector = args and args[0] == dre.selector

    if validation:
        if argnum_one_more:
            if not arg0_is_selector:
                with pytest.raises(AssertionError) as ae:
                    dre._executor_prep(args)

                assert "should have been the selector" in str(ae.value)
                return

        if not (argnum_same or argnum_one_more):
            with pytest.raises(AssertionError) as ae:
                dre._executor_prep(args)

            assert "is incompatible with" in str(ae.value)
            return

        try:
            prefix = tuple() if omit_method_selector else ("blah",)
            type_prefix = [] if omit_method_selector else [None]
            encoded_args = DryRunEncoder.encode_args(
                prefix + args,
                type_prefix + dre.abi_argument_types,
                validation=validation,
            )
        except AssertionError as encode_args_ae:
            with pytest.raises(AssertionError) as ae:
                dre._executor_prep(args)
            assert "problem encoding arg" in str(encode_args_ae)
            assert str(ae.value) == str(encode_args_ae)
            return

        args_out, encoded_args_out = dre._executor_prep(args)
        argslen = len(args)
        aolen = len(args_out)
        arg_range = slice(aolen - argslen, aolen)
        assert args_out[arg_range] == args
        assert len(encoded_args_out) == len(encoded_args)
        assert encoded_args_out[arg_range] == encoded_args[arg_range]
        return

    assert validation is False
    assert aats_out_is_none is False, "already considered this"

    try:
        encoded_args = DryRunEncoder.encode_args(
            args[1 - int(omit_method_selector) :],
            dre.abi_argument_types[1 - int(omit_method_selector) :],
            validation=validation,
        )
    except AssertionError as encode_args_ae:
        with pytest.raises(AssertionError) as ae:
            dre._executor_prep(args)
        assert "problem encoding arg" in str(encode_args_ae)
        assert "problem encoding arg" in str(ae)
        return

    args_out, encoded_args_out = dre._executor_prep(args)
    bidx = 1 - int(omit_method_selector)
    assert args_out[bidx:] == args[bidx:]
    assert encoded_args_out[bidx:] == encoded_args


def test_ABIMethodCallStrategy_init():
    teal = "blah some teal"
    contract = "very bad contract"
    method: Optional[str] = "non existant method"
    argument_strategy = RandomABIStrategyHalfSized
    num_dryruns = Mock(int)
    handle_selector = Mock(bool)
    abi_args_mod: Optional[ABIArgsMod] = None

    # fail as the contract is garbage
    with pytest.raises(JSONDecodeError):
        ABIMethodCallStrategy(
            teal,
            contract,
            method,
            argument_strategy,
            num_dryruns=num_dryruns,
            handle_selector=handle_selector,
            abi_args_mod=abi_args_mod,
        )

    # ok, let's give a real contract
    # but we'll fail because the method is garbage so doesn't exist in the contract
    contract = '{"name":"ExampleContract","desc":"This is an example contract","networks":{"wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8=":{"appID":1234},"SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=":{"appID":5678}},"methods":[{"name":"add","args":[{"type":"uint32"},{"type":"uint32"}],"returns":{"type":"uint32"}}]}'
    with pytest.raises(KeyError) as ke:
        ABIMethodCallStrategy(
            teal,
            contract,
            method,
            argument_strategy,
            num_dryruns=num_dryruns,
            handle_selector=handle_selector,
            abi_args_mod=abi_args_mod,
        )
    assert f"found 0 methods for {method}" in str(ke.value)

    # finally pass with an actual contract method:
    method = "add"
    amcs = ABIMethodCallStrategy(
        teal,
        contract,
        method,
        argument_strategy,
        num_dryruns=num_dryruns,
        handle_selector=handle_selector,
        abi_args_mod=abi_args_mod,
    )
    assert amcs.program is teal
    assert (
        isinstance(amcs.contract, Contract)
        and "add" == amcs.contract.dictify()["methods"][0]["name"]
    )
    assert amcs.method is method
    assert amcs.argument_strategy is argument_strategy
    assert amcs.num_dryruns == num_dryruns
    assert amcs.handle_selector is handle_selector
    assert amcs.abi_args_mod is abi_args_mod

    # bare app call:
    method = None
    amcs = ABIMethodCallStrategy(
        teal,
        contract,
        method,
        argument_strategy,
        num_dryruns=num_dryruns,
        handle_selector=handle_selector,
        abi_args_mod=abi_args_mod,
    )
    assert amcs.program is teal
    assert (
        isinstance(amcs.contract, Contract)
        and "add" == amcs.contract.dictify()["methods"][0]["name"]
    )
    assert amcs.method is method
    assert amcs.argument_strategy is argument_strategy
    assert amcs.num_dryruns == num_dryruns
    assert amcs.handle_selector is handle_selector
    assert amcs.abi_args_mod is abi_args_mod

    # what about defaults?
    amcs = ABIMethodCallStrategy(
        teal,
        contract,
        method,
    )
    assert amcs.program is teal
    assert (
        isinstance(amcs.contract, Contract)
        and "add" == amcs.contract.dictify()["methods"][0]["name"]
    )
    assert amcs.method is method
    assert amcs.argument_strategy is RandomABIStrategy
    assert amcs.num_dryruns == 1
    assert amcs.handle_selector is True
    assert amcs.abi_args_mod is None
