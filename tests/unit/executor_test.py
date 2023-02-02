from dataclasses import asdict
import pytest
from unittest.mock import Mock

from algosdk.transaction import StateSchema
from algosdk.error import ABIEncodingError
from algosdk.v2client.algod import AlgodClient


from graviton.blackbox import DryRunExecutor, DryRunEncoder, DryRunTransactionParams
from graviton.models import ExecutionMode


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

    start_from: int = 1 - int(omit_method_selector)
    try:
        encoded_args = DryRunEncoder.encode_args(
            args[start_from:],
            dre.abi_argument_types[start_from:],
            validation=validation,
        )
    except AssertionError as encode_args_ae:
        with pytest.raises(AssertionError) as ae:
            dre._executor_prep(args)
        assert "problem encoding arg" in str(encode_args_ae)
        assert "problem encoding arg" in str(ae)
        return

    args_out, encoded_args_out = dre._executor_prep(args)
    assert args_out[start_from:] == args[start_from:]
    assert encoded_args_out[start_from:] == encoded_args


def test_DryRunTransactionParams_update():
    drtp1 = DryRunTransactionParams(
        sender="sender", lease="123", amt=456, global_schema=StateSchema(1, 2)
    )

    with pytest.raises(AssertionError, match=r".*can't update.*str."):
        drtp1.update("I'm not the wrong type")  # type: ignore

    drtp2 = DryRunTransactionParams(
        sender=None, lease="789", amt=None, local_schema=StateSchema(4, 5)
    )

    drtp1.update(drtp2)

    # drpt2 is unchanged:
    assert drtp2.sender is None
    assert drtp2.lease == "789"
    assert drtp2.amt is None
    assert drtp2.global_schema is None
    assert drtp2.local_schema == StateSchema(4, 5)
    explitly_asserted = ["sender", "lease", "amt", "global_schema", "local_schema"]
    for k, v in asdict(drtp2).items():
        if k not in explitly_asserted:
            assert not v

    # drpt1 is updated:
    assert drtp1.sender == "sender"
    assert drtp1.lease == "789"
    assert drtp1.amt == 456
    assert drtp1.global_schema == StateSchema(1, 2)
    assert drtp1.local_schema == StateSchema(4, 5)
    for k, v in asdict(drtp1).items():
        if k not in explitly_asserted:
            assert not v
