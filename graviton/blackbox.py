from copy import copy
from dataclasses import asdict, dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    Final,
    List,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    cast,
)

from algosdk import abi
from algosdk import atomic_transaction_composer as atc
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.models import DryrunRequest
from algosdk.transaction import (
    OnComplete,
    StateSchema,
    SuggestedParams,
)

from graviton.dryrun import DryRunHelper
from graviton.inspector import DryRunInspector, EncodingType
from graviton.models import (
    ArgType,
    DryRunAccountType,
    ExecutionMode,
    PyTypes,
    Stringy,
    ZERO_ADDRESS,
)

TealAndMethodType = Union[Tuple[str], Tuple[str, str]]

T = TypeVar("T")

OneOrMany = Union[T, Sequence[T]]


MAX_APP_ARG_LIMIT = atc.AtomicTransactionComposer.MAX_APP_ARG_LIMIT
# `CREATION_APP_CALL` and `EXISTING_APP_CALL` are enum-like constants used to denote whether a dry run
# execution will simulate calling during on-creation vs post-creation.
# In the default case that a dry run is executed without a provided application id (aka `index`), the `index`
# supplied will be:
# * `CREATION_APP_CALL` in the case of `is_app_create == True`
# * `EXISTING_APP_CALL` in the case of `is_app_create == False`
CREATION_APP_CALL: Final[int] = 0
EXISTING_APP_CALL: Final[int] = 42

SUGGESTED_PARAMS = SuggestedParams(int(1000), int(1), int(100), "", flat_fee=True)


class DryRunEncoder:
    """Encoding utilities for dry run executions and results"""

    @classmethod
    def encode_args(
        cls,
        args: Sequence[PyTypes],
        abi_types: Optional[List[EncodingType]] = None,
        validation: bool = True,
    ) -> List[ArgType]:
        """
        Encoding convention for Black Box Testing.

        * Assumes int's are uint64 and encodes them as such
        * Leaves str's alone

        Arguments:
            args - the dry-run arguments to be encoded

            abi_types (optional) - When present this list needs to be the same length as `args`.
                When `None` is supplied as the abi_type, the corresponding element of `args` is not encoded.

            validation (optional) - This should usually be left `True` which
                ensures that -in the case of ABI typing- the number of types is
                exactly the number of args. However, in the case that the 0'th argument
                already includes the method selector, `validation` can be set `False`
                which allows the automatic prepending of `None` to the ABI types list.
        """
        a_len = len(args)
        if abi_types is not None:
            t_len = len(abi_types)
            if validation:
                assert (
                    a_len == t_len
                ), f"mismatch between args (length={a_len}) and abi_types (length={t_len})"
            elif a_len > t_len:
                abi_types = abi_types + [None] * (a_len - t_len)

        if a_len <= MAX_APP_ARG_LIMIT:
            return [
                cls._encode_arg(a, i, abi_types[i] if abi_types else None)
                for i, a in enumerate(args)
            ]

        assert (
            abi_types
        ), f"for non-ABI app calls, there is no specification for encoding more than {MAX_APP_ARG_LIMIT} arguments. But encountered an app call attempt with {a_len} arguments"

        final_index = MAX_APP_ARG_LIMIT - 1
        simple_15 = [
            cls._encode_arg(a, i, abi_types[i])
            for i, a in enumerate(args)
            if i < final_index
        ]
        jammed_in = cls._encode_arg(
            args[final_index:],
            final_index,
            abi_type=abi.TupleType(abi_types[final_index:]),
        )
        return simple_15 + [jammed_in]

    @classmethod
    def hex0x(cls, x) -> str:
        return f"0x{cls.hex(x)}"

    @classmethod
    def hex(cls, out: Union[int, str]) -> str:
        """
        Encoding convention for Black Box Testing.

        * Assumes int's are uint64
        * Assumes everything else is a str
        * Encodes them into hex str's
        """
        cls._partial_encode_assert(out, None)
        return cast(bytes, cls._to_bytes(out)).hex()

    @classmethod
    def _to_bytes(
        cls, x: Union[int, str, bytes], only_attempt_int_conversion=False
    ) -> Union[int, str, bytes]:
        """
        NOTE: When only_attempt_int_conversion=False the output is guaranteed to be `bytes` (when no error)
        """
        if isinstance(x, bytes):
            return x

        is_int = isinstance(x, int)
        if only_attempt_int_conversion and not is_int:
            return x

        return (
            cast(int, x).to_bytes(8, "big") if is_int else bytes(cast(str, x), "utf-8")
        )

    @classmethod
    def _encode_arg(
        cls, arg: PyTypes, idx: int, abi_type: EncodingType
    ) -> Union[str, bytes]:
        partial = cls._partial_encode_assert(
            arg, abi_type, f"problem encoding arg ({arg!r}) at index ({idx})"
        )
        if partial is not None:
            return cast(bytes, partial)

        # BELOW:
        # bytes -> bytes
        # int -> bytes
        # str -> str
        return cast(
            Union[str, bytes],
            cls._to_bytes(
                cast(Union[int, str, bytes], arg), only_attempt_int_conversion=True
            ),
        )

    @classmethod
    def _partial_encode_assert(
        cls, arg: PyTypes, abi_type: EncodingType, msg: str = ""
    ) -> Optional[bytes]:
        """
        When have an `abi_type` is present, attempt to encode `arg` accordingly (returning `bytes`)
        ELSE: assert the type is one of `(bytes, int, str)` returning `None`
        """
        if abi_type:
            try:
                return cast(abi.ABIType, abi_type).encode(arg)
            except Exception as e:
                raise AssertionError(
                    f"{msg +': ' if msg else ''}can't handle arg [{arg!r}] of type {type(arg)} and abi-type {abi_type}: {e}"
                )
        assert isinstance(
            arg, (bytes, int, str)
        ), f"{msg +': ' if msg else ''}can't handle arg [{arg!r}] of type {type(arg)}"
        if isinstance(arg, int):
            assert arg >= 0, f"can't handle negative arguments but was given {arg}"
        return None


@dataclass
class DryRunTransactionParams:

    # generic:
    sender: Optional[Stringy] = None
    sp: Optional[SuggestedParams] = None
    note: Optional[Stringy] = None
    lease: Optional[Stringy] = None
    rekey_to: Optional[Stringy] = None
    # payments
    receiver: Optional[Stringy] = None
    amt: Optional[int] = None
    close_remainder_to: Optional[Stringy] = None
    # apps
    index: Optional[int] = None
    on_complete: Optional[OnComplete] = None
    local_schema: Optional[StateSchema] = None
    global_schema: Optional[StateSchema] = None
    approval_program: Optional[str] = None
    clear_program: Optional[str] = None
    app_args: Optional[Sequence[ArgType]] = None
    accounts: Optional[List[str]] = None
    foreign_apps: Optional[List[str]] = None
    foreign_assets: Optional[List[str]] = None
    extra_pages: Optional[int] = None
    dryrun_accounts: List[DryRunAccountType] = field(
        default_factory=list
    )  # belongs here???
    # future:
    box_refs: Optional[List[Tuple[int, str]]] = None

    @classmethod
    def for_logicsig(
        cls,
        sender: Optional[Stringy] = None,
        sp: Optional[SuggestedParams] = None,
        note: Optional[Stringy] = None,
        lease: Optional[Stringy] = None,
        rekey_to: Optional[Stringy] = None,
        receiver: Optional[Stringy] = None,
        amt: Optional[int] = None,
        close_remainder_to: Optional[Stringy] = None,
    ) -> "DryRunTransactionParams":
        return cls(
            sender=sender or ZERO_ADDRESS,
            sp=sp or SUGGESTED_PARAMS,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
            receiver=receiver or ZERO_ADDRESS,
            amt=0 if amt is None else amt,
            close_remainder_to=close_remainder_to,
        )

    @classmethod
    def for_app(
        cls,
        is_app_create: bool = False,
        sender: Optional[Stringy] = None,
        sp: Optional[SuggestedParams] = None,
        note: Optional[Stringy] = None,
        lease: Optional[Stringy] = None,
        rekey_to: Optional[Stringy] = None,
        index: Optional[int] = None,
        on_complete: Optional[OnComplete] = None,
        local_schema: Optional[StateSchema] = None,
        global_schema: Optional[StateSchema] = None,
        approval_program: Optional[str] = None,
        clear_program: Optional[str] = None,
        app_args: Optional[Sequence[ArgType]] = None,
        accounts: Optional[List[str]] = None,
        foreign_apps: Optional[List[str]] = None,
        foreign_assets: Optional[List[str]] = None,
        extra_pages: Optional[int] = None,
        dryrun_accounts: List[DryRunAccountType] = [],
    ):
        return cls(
            sender=sender or ZERO_ADDRESS,
            sp=sp or SUGGESTED_PARAMS,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
            index=(CREATION_APP_CALL if is_app_create else EXISTING_APP_CALL)
            if index is None
            else index,
            on_complete=on_complete,
            local_schema=local_schema,
            global_schema=global_schema,
            approval_program=approval_program,
            clear_program=clear_program,
            app_args=app_args,
            accounts=accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
            extra_pages=extra_pages,
            dryrun_accounts=dryrun_accounts,
        )

    def asdict(self, drop_nones: bool = True) -> Dict[str, Any]:
        d = asdict(self)
        del d["dryrun_accounts"]
        del d["box_refs"]
        if not drop_nones:
            return d

        return {k: v for k, v in d.items() if v is not None}

    def update_fields(self, other: "DryRunTransactionParams") -> None:
        assert isinstance(
            other, DryRunTransactionParams
        ), f"can't update {type(self)} using {type(other)}"

        # NOTE: confusingly, we're using `dataclasses.dict` here to not drop any fields
        for k, v in asdict(other).items():
            if v is not None:
                setattr(self, k, v)


class DryRunExecutor:

    """Methods to package up and kick off dry run executions"""

    # for usage convenience, copy constants over into the class
    CREATION_APP_CALL = CREATION_APP_CALL
    EXISTING_APP_CALL = EXISTING_APP_CALL

    SUGGESTED_PARAMS = SUGGESTED_PARAMS

    def __init__(
        self,
        algod: AlgodClient,
        mode: ExecutionMode,
        teal: str,
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: bool = False,
        validation: bool = True,
    ):
        self.algod: AlgodClient = algod
        self.mode: ExecutionMode = mode
        self.program: str = teal
        self.abi_method_signature: Optional[str] = abi_method_signature
        self.omit_method_selector: bool = omit_method_selector
        self.validation: bool = validation

        self.is_app: bool
        self.abi_argument_types: Optional[List[EncodingType]]
        self.abi_return_type: Optional[EncodingType]
        self.method: Optional[abi.Method]
        self.selector: Optional[bytes]

        (
            self.is_app,
            self.abi_argument_types,
            self.abi_return_type,
            self.method,
            self.selector,
        ) = self._init_impl(self.mode, self.abi_method_signature)

    @classmethod
    def _init_impl(
        cls, mode: ExecutionMode, abi_method_signature: Optional[str]
    ) -> Tuple[
        bool,
        Optional[List[EncodingType]],
        Optional[Union[abi.ABIType, str]],
        Optional[abi.Method],
        Optional[bytes],
    ]:
        assert (
            len(ExecutionMode) == 2
        ), f"assuming only 2 ExecutionMode's but have {len(ExecutionMode)}"
        assert mode in ExecutionMode, f"unknown mode {mode} of type {type(mode)}"
        is_app = mode == ExecutionMode.Application

        method: Optional[abi.Method] = None
        selector: Optional[bytes] = None
        abi_argument_types: Optional[List[EncodingType]] = None
        abi_return_type: Optional[Union[abi.ABIType, str]] = None

        if abi_method_signature:
            method = abi.Method.from_signature(abi_method_signature)
            selector = method.get_selector()
            abi_argument_types = [a.type for a in method.args]

            if method.returns.type != abi.Returns.VOID:
                abi_return_type = method.returns.type

        return is_app, abi_argument_types, abi_return_type, method, selector

    def run_one(
        self,
        args: Sequence[PyTypes],
        *,
        txn_params: Optional[DryRunTransactionParams] = None,
        verbose: bool = False,
    ) -> DryRunInspector:
        """Convenience method for easier typing - executes a single dry run"""
        return cast(
            DryRunInspector,
            self._run(tuple(args), txn_params=txn_params, verbose=verbose),
        )

    def run_sequence(
        self,
        inputs: Sequence[Sequence[PyTypes]],
        *,
        txn_params: Optional[DryRunTransactionParams] = None,
        verbose: bool = False,
    ) -> Sequence[DryRunInspector]:
        """Convenience method for easier typing - executes dry run sequence"""
        return cast(
            Sequence[DryRunInspector],
            self._run(
                [tuple(args) for args in inputs], txn_params=txn_params, verbose=verbose
            ),
        )

    @classmethod
    def multi_exec(
        cls,
        execs: List["DryRunExecutor"],
        inputs: Sequence[Sequence[PyTypes]],
        *,
        txn_params: Optional[DryRunTransactionParams] = None,
        verbose: bool = False,
    ) -> Sequence[Sequence[DryRunInspector]]:
        return [
            cast(
                Sequence[DryRunInspector],
                e._run(inputs, txn_params=txn_params, verbose=verbose),
            )
            for e in execs
        ]

    def _run(
        self,
        inputs: OneOrMany[Sequence[PyTypes]],
        *,
        txn_params: Optional[DryRunTransactionParams] = None,
        verbose: bool = False,
    ) -> OneOrMany[DryRunInspector]:
        """
        Be careful when using this private method. Its behavior depends on the following type-switch:
        * when `inputs` is a tuple ---> interpret this to be a single `args` tuple and run a single dry run
        * otherwise ---> we require `inputs` to either be a `list` or a `map`, and take a dry-run for every element in the sequence
        """
        executor = self._executor(txn_params, verbose)
        if isinstance(inputs, tuple):
            return executor(inputs)

        assert isinstance(
            inputs, (list, map)
        ), f"inputs must be of type list or map (for multiple args) or tuple (for single args) but was {type(inputs)}"
        if isinstance(inputs, map):
            inputs = list(inputs)

        assert inputs, "must provide at least one input args tuple"

        for i, args in enumerate(inputs):
            assert isinstance(
                args, tuple
            ), f"each args in inputs list must be a tuple but at index {i=} we have {type(args)}"

        inputs = cast(List[Tuple[PyTypes, ...]], inputs)
        return list(map(executor, inputs))

    def _executor(
        self,
        txn_params: Optional[DryRunTransactionParams],
        verbose: bool,
    ) -> Callable[[Tuple[PyTypes, ...]], DryRunInspector]:
        def executor(args: Tuple[PyTypes, ...]) -> DryRunInspector:
            args, encoded_args = self._executor_prep(args)

            dryrun_req: DryrunRequest
            txn_params_d = txn_params.asdict() if txn_params else {}
            dr_acts = txn_params.dryrun_accounts if txn_params else []
            if self.is_app:
                dryrun_req = DryRunHelper.singleton_app_request(
                    self.program,
                    encoded_args,
                    txn_params_d,
                    dr_acts,
                )
            else:
                dryrun_req = DryRunHelper.singleton_logicsig_request(
                    self.program, encoded_args, txn_params_d
                )
            if verbose:
                print(f"{type(self)}._run(): {dryrun_req=}")
            dryrun_resp = self.algod.dryrun(dryrun_req)
            if verbose:
                print(f"{type(self)}::_executor(): {dryrun_resp=}")
            return DryRunInspector.from_single_response(
                dryrun_resp, args, encoded_args, abi_type=self.abi_return_type
            )

        return executor

    def _executor_prep(
        self, args: Tuple[PyTypes, ...]
    ) -> Tuple[Tuple[PyTypes, ...], List[ArgType]]:
        abi_argument_types = self.abi_argument_types
        if self.abi_method_signature:
            args, abi_argument_types = self._abi_adapter(args)

        encoded_args = DryRunEncoder.encode_args(
            args, abi_types=abi_argument_types, validation=self.validation
        )
        return args, encoded_args

    def _abi_adapter(
        self, args: Sequence[PyTypes]
    ) -> Tuple[Tuple[PyTypes, ...], Optional[List[EncodingType]]]:
        """
        Validate and possibly return modified versions of:
        * args
        * abi_argument_types
        """
        args_out = list(args)
        aats_out = copy(self.abi_argument_types)
        nope: EncodingType = None
        if self.validation:
            assert aats_out is not None, "unexpected None"
            assert self.method is not None, "unexpected None"
            assert self.selector is not None, "unexpected None"
            aats_out = cast(List[EncodingType], aats_out)
            method = cast(abi.Method, self.method)
            selector = cast(PyTypes, self.selector)
            if len(args_out) == len(aats_out):
                if not self.omit_method_selector:
                    # the method selector is not abi-encoded, hence its abi-type is set to None
                    aats_out = [None] + aats_out
                    args_out = [selector] + args_out

            elif len(args_out) == len(aats_out) + 1:
                assert (
                    args_out[0] == selector
                ), f"{args_out[0]=} should have been the {selector=}"

                if self.omit_method_selector:
                    args_out = args_out[1:]
                else:
                    aats_out = [nope] + aats_out

            else:
                raise AssertionError(
                    f"{len(args_out)=} is incompatible with {len(method.args)=}: LEFT should be equal or exactly RIGHT + 1"
                )
        elif not self.omit_method_selector:
            assert aats_out is not None
            aats_out = [nope] + cast(List[EncodingType], aats_out)
        # else: not validating + omitting method selector ==> aats_out == abi_argument_types

        return tuple(args_out), aats_out
