from graviton.abi_strategy import PyTypes, ABIStrategy, RandomABIStrategy
from graviton.dryrun import DryRunHelper
from graviton.inspector import DryRunInspector
from graviton.models import ZERO_ADDRESS, ArgType, DryRunAccountType, ExecutionMode


from typing import (
    Any,
    Dict,
    Final,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
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


TealAndMethodType = Union[Tuple[str], Tuple[str, str]]
EncodingType = Union[abi.ABIType, str, None]


MAX_APP_ARG_LIMIT = atc.AtomicTransactionComposer.MAX_APP_ARG_LIMIT


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
        if abi_types:
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


class DryRunExecutor:
    """Methods to package up and kick off dry run executions

    When executing an A.B.I. compliant dry-run specify `abi_argument_types` as well as an `abi_return_type`:
       * `abi_argument_types` are handed off to the `DryRunEncoder` for encoding purposes
       * `abi_return_type` is given the `DryRunInspector`'s resulting from execution for ABI-decoding into Python
    """

    # `CREATION_APP_CALL` and `EXISTING_APP_CALL` are enum-like constants used to denote whether a dry run
    # execution will simulate calling during on-creation vs post-creation.
    # In the default case that a dry run is executed without a provided application id (aka `index`), the `index`
    # supplied will be:
    # * `CREATION_APP_CALL` in the case of `is_app_create == True`
    # * `EXISTING_APP_CALL` in the case of `is_app_create == False`
    CREATION_APP_CALL: Final[int] = 0
    EXISTING_APP_CALL: Final[int] = 42

    SUGGESTED_PARAMS = SuggestedParams(int(1000), int(1), int(100), "", flat_fee=True)

    @classmethod
    def dryrun_app(
        cls,
        algod: AlgodClient,
        teal: str,
        args: Sequence[PyTypes],
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        sender: Optional[str] = None,
        sp: Optional[SuggestedParams] = None,
        index: Optional[int] = None,
        local_schema: Optional[StateSchema] = None,
        global_schema: Optional[StateSchema] = None,
        approval_program: Optional[str] = None,
        clear_program: Optional[str] = None,
        app_args: Optional[Sequence[Union[str, int]]] = None,
        accounts: Optional[List[str]] = None,
        foreign_apps: Optional[List[str]] = None,
        foreign_assets: Optional[List[str]] = None,
        note: Optional[str] = None,
        lease: Optional[str] = None,
        rekey_to: Optional[str] = None,
        extra_pages: Optional[int] = None,
        dryrun_accounts: List[DryRunAccountType] = [],
    ) -> "DryRunInspector":
        """
        Execute a dry run to simulate an app call using provided:

            * algod
            * teal program for the approval (or clear in the case `on_complete=OnComplete.ClearStateOC`)
            * args - the application arguments as Python types
            * abi_argument_types - ABI types of the arguments, in the case of an ABI method call
            * abi_return_type - the ABI type returned, in the case of an ABI method call
            * is_app_create to indicate whether or not to simulate an app create call
            * on_complete - the OnComplete that should be provided in the app call transaction

        Additional application call transaction parameters can be provided as well
        """
        return cls.execute_one_dryrun(
            algod,
            teal,
            args,
            ExecutionMode.Application,
            abi_method_signature=abi_method_signature,
            omit_method_selector=omit_method_selector,
            validation=validation,
            txn_params=cls.transaction_params(
                sender=ZERO_ADDRESS if sender is None else sender,
                sp=cls.SUGGESTED_PARAMS if sp is None else sp,
                note=note,
                lease=lease,
                rekey_to=rekey_to,
                index=(
                    (cls.CREATION_APP_CALL if is_app_create else cls.EXISTING_APP_CALL)
                    if index is None
                    else index
                ),
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
            ),
            accounts=dryrun_accounts,
        )

    @classmethod
    def dryrun_logicsig(
        cls,
        algod: AlgodClient,
        teal: str,
        args: Sequence[PyTypes],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        sender: str = ZERO_ADDRESS,
        sp: Optional[SuggestedParams] = None,
        receiver: Optional[str] = None,
        amt: Optional[int] = None,
        close_remainder_to: Optional[str] = None,
        note: Optional[str] = None,
        lease: Optional[str] = None,
        rekey_to: Optional[str] = None,
    ) -> "DryRunInspector":
        return cls.execute_one_dryrun(
            algod,
            teal,
            args,
            ExecutionMode.Signature,
            abi_method_signature=abi_method_signature,
            omit_method_selector=omit_method_selector,
            validation=validation,
            txn_params=cls.transaction_params(
                sender=ZERO_ADDRESS if sender is None else sender,
                sp=cls.SUGGESTED_PARAMS if sp is None else sp,
                note=note,
                lease=lease,
                rekey_to=rekey_to,
                receiver=ZERO_ADDRESS if receiver is None else receiver,
                amt=0 if amt is None else amt,
                close_remainder_to=close_remainder_to,
            ),
        )

    @classmethod
    def dryrun_app_pair_on_sequence(
        cls,
        algod: AlgodClient,
        teal_and_method1: TealAndMethodType,
        teal_and_method2: TealAndMethodType,
        inputs: List[Sequence[PyTypes]],
        *,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        dryrun_accounts: List[DryRunAccountType] = [],
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
    ) -> Tuple[Sequence["DryRunInspector"], Sequence["DryRunInspector"]]:
        return tuple(  # type: ignore
            cls.dryrun_multiapps_on_sequence(
                algod=algod,
                multi_teal_method_pairs=[teal_and_method1, teal_and_method2],
                inputs=inputs,
                is_app_create=is_app_create,
                on_complete=on_complete,
                dryrun_accounts=dryrun_accounts,
                omit_method_selector=omit_method_selector,
                validation=validation,
            )
        )

    @classmethod
    def dryrun_multiapps_on_sequence(
        cls,
        algod: AlgodClient,
        multi_teal_method_pairs: List[TealAndMethodType],
        inputs: List[Sequence[PyTypes]],
        *,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        dryrun_accounts: List[DryRunAccountType] = [],
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
    ) -> List[Sequence["DryRunInspector"]]:
        def runner(teal_method_pair):
            teal = teal_method_pair[0]
            abi_method = None
            if len(teal_method_pair) > 1:
                abi_method = teal_method_pair[1]

            return cls.dryrun_app_on_sequence(
                algod=algod,
                teal=teal,
                inputs=inputs,
                abi_method_signature=abi_method,
                omit_method_selector=omit_method_selector,
                validation=validation,
                is_app_create=is_app_create,
                on_complete=on_complete,
                dryrun_accounts=dryrun_accounts,
            )

        return list(map(runner, multi_teal_method_pairs))

    @classmethod
    def dryrun_app_on_sequence(
        cls,
        algod: AlgodClient,
        teal: str,
        inputs: List[Sequence[PyTypes]],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        dryrun_accounts: List[DryRunAccountType] = [],
    ) -> List["DryRunInspector"]:
        # TODO: handle txn_params
        return list(
            map(
                lambda args: cls.dryrun_app(
                    algod=algod,
                    teal=teal,
                    args=args,
                    abi_method_signature=abi_method_signature,
                    omit_method_selector=omit_method_selector,
                    validation=validation,
                    is_app_create=is_app_create,
                    on_complete=on_complete,
                    dryrun_accounts=dryrun_accounts,
                ),
                inputs,
            )
        )

    @classmethod
    def dryrun_logicsig_on_sequence(
        cls,
        algod: AlgodClient,
        teal: str,
        inputs: List[Sequence[PyTypes]],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
    ) -> List["DryRunInspector"]:
        # TODO: handle txn_params
        return list(
            map(
                lambda args: cls.dryrun_logicsig(
                    algod=algod,
                    teal=teal,
                    args=args,
                    abi_method_signature=abi_method_signature,
                    omit_method_selector=omit_method_selector,
                    validation=validation,
                ),
                inputs,
            )
        )

    @classmethod
    def execute_one_dryrun(
        cls,
        algod: AlgodClient,
        teal: str,
        args: Sequence[PyTypes],
        mode: ExecutionMode,
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        txn_params: dict = {},
        accounts: List[DryRunAccountType] = [],
        verbose: bool = False,
    ) -> "DryRunInspector":
        assert (
            len(ExecutionMode) == 2
        ), f"assuming only 2 ExecutionMode's but have {len(ExecutionMode)}"
        assert mode in ExecutionMode, f"unknown mode {mode} of type {type(mode)}"
        is_app = mode == ExecutionMode.Application

        abi_argument_types: Optional[List[EncodingType]] = None
        abi_return_type: Optional[abi.ABIType] = None
        if abi_method_signature:
            """
            Try to do the right thing.
            When `omit_method_selector is False`:
                * if provided with the same number of args as expected arg types
                    --> prepend `None` to the types and `selector` to args
                * if provided with |arg types| + 1 args
                    --> assert that `args[0] == selector`
                * otherwise
                    --> there is a cardinality mismatch, so fail
            When `omit_method_selector is True`:
                * if provided with the same number of args as expected arg types
                    --> good to go
                * if provided with |arg types| + 1 args
                    --> assert that `args[0] == selector` but DROP it from the args
                * otherwise
                    --> there is a cardinality mismatch, so fail
            """
            method = abi.Method.from_signature(abi_method_signature)
            selector = method.get_selector()
            abi_argument_types = [a.type for a in method.args]

            if validation:
                args = list(args)
                if len(args) == len(abi_argument_types):
                    if not omit_method_selector:
                        # the method selector is not abi-encoded, hence its abi-type is set to None
                        abi_argument_types = [None] + abi_argument_types  # type: ignore
                        args = [selector] + args

                elif len(args) == len(abi_argument_types) + 1:
                    assert (
                        args[0] == selector
                    ), f"{args[0]=} should have been the {selector=}"

                    if omit_method_selector:
                        args = args[1:]
                    else:
                        abi_argument_types = [None] + abi_argument_types  # type: ignore

                else:
                    raise AssertionError(
                        f"{len(args)=} is incompatible with {len(method.args)=}: LEFT should be equal or exactly RIGHT + 1"
                    )
            elif not omit_method_selector:
                abi_argument_types = [None] + abi_argument_types  # type: ignore

            args = tuple(args)

            if method.returns.type != abi.Returns.VOID:
                abi_return_type = cast(abi.ABIType, method.returns.type)

        encoded_args = DryRunEncoder.encode_args(
            args, abi_types=abi_argument_types, validation=validation
        )

        dryrun_req: DryrunRequest
        if is_app:
            dryrun_req = DryRunHelper.singleton_app_request(
                teal, encoded_args, txn_params, accounts
            )
        else:
            dryrun_req = DryRunHelper.singleton_logicsig_request(
                teal, encoded_args, txn_params
            )
        if verbose:
            print(f"{cls}::execute_one_dryrun(): {dryrun_req=}")
        dryrun_resp = algod.dryrun(dryrun_req)
        if verbose:
            print(f"{cls}::execute_one_dryrun(): {dryrun_resp=}")
        return DryRunInspector.from_single_response(
            dryrun_resp, args, encoded_args, abi_type=cast(abi.ABIType, abi_return_type)
        )

    @classmethod
    def transaction_params(
        cls,
        *,
        # generic:
        sender: Optional[str] = None,
        sp: Optional[SuggestedParams] = None,
        note: Optional[str] = None,
        lease: Optional[str] = None,
        rekey_to: Optional[str] = None,
        # payments:
        receiver: Optional[str] = None,
        amt: Optional[int] = None,
        close_remainder_to: Optional[str] = None,
        # apps:
        index: Optional[int] = None,
        on_complete: Optional[OnComplete] = None,
        local_schema: Optional[StateSchema] = None,
        global_schema: Optional[StateSchema] = None,
        approval_program: Optional[str] = None,
        clear_program: Optional[str] = None,
        app_args: Optional[Sequence[Union[str, int]]] = None,
        accounts: Optional[List[str]] = None,
        foreign_apps: Optional[List[str]] = None,
        foreign_assets: Optional[List[str]] = None,
        extra_pages: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Returns a `dict` with keys the same as method params, after removing all `None` values
        """
        params = dict(
            sender=sender,
            sp=sp,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
            receiver=receiver,
            amt=amt,
            close_remainder_to=close_remainder_to,
            index=index,
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
        )
        return {k: v for k, v in params.items() if v is not None}


class ABIContractExecutor:
    """Execute an ABI Contract via Dry Run"""

    def __init__(
        self,
        teal: str,
        contract: str,
        argument_strategy: Optional[Type[ABIStrategy]] = RandomABIStrategy,
        dry_runs: int = 1,
        handle_selector: bool = False,
    ):
        """
        teal - The program to run

        contract - ABI Contract JSON

        argument_strategy (optional) - strategy for generating arguments

        dry_runs (default=1) - the number of dry runs to run
            (generates different inputs each time)

        handle_selector - usually we'll want to let `DryRunExecutor.execute_one_dryrun()`
            handle adding the method selector so this param
            should _probably_ be left False. But when set True, when providing `inputs`
            ensure that the 0'th argument for method calls is the selector.
            And when set True, when NOT providing `inputs`, the selector arg
            at index 0 will be added automatically.
        """
        self.program = teal
        self.contract: abi.Contract = abi.Contract.from_json(contract)
        self.argument_strategy: Optional[Type[ABIStrategy]] = argument_strategy
        self.dry_runs = dry_runs
        self.handle_selector = handle_selector

    def method_signature(self, method: Optional[str]) -> Optional[str]:
        """Returns None, for a bare app call (method=None signals this)"""
        if not method:
            return None

        return self.contract.get_method_by_name(method).get_signature()

    def argument_types(self, method: Optional[str] = None) -> List[abi.ABIType]:
        """
        Argument types (excluding selector)
        """
        if not method:
            return []

        return [
            cast(abi.ABIType, arg.type)
            for arg in self.contract.get_method_by_name(method).args
        ]

    def generate_inputs(self, method: Optional[str]) -> List[Sequence[PyTypes]]:
        """
        Generates inputs appropriate for bare app call,
        AND appropirate for method calls, if put starting at index = 1.
        Uses available argument_strategy.
        """
        assert (
            self.argument_strategy
        ), "cannot generate inputs without an argument_strategy"

        if not method:
            # bare calls receive no arguments
            return [tuple() for _ in range(self.dry_runs)]

        arg_types = self.argument_types(method)
        prefix = []
        if self.handle_selector and method:
            prefix = [self.contract.get_method_by_name(method).get_selector()]

        def gen_args():
            return tuple(
                prefix
                + [self.argument_strategy(arg_type).get() for arg_type in arg_types]
            )

        return [gen_args() for _ in range(self.dry_runs)]

    def validate_inputs(self, method: Optional[str], inputs: List[Sequence[PyTypes]]):
        """TODO: add type validation for arguments"""

        if not method:
            assert not any(
                inputs
            ), f"bare app calls require args to be empty but inputs={inputs}"
            return

        arg_types = self.argument_types(method)
        selector_if_needed: Optional[bytes] = None
        if self.handle_selector:
            selector_if_needed = self.contract.get_method_by_name(method).get_selector()

        error = None
        for i, args in enumerate(inputs):
            targs = cast(tuple, args)
            if selector_if_needed:
                pfx = f"args at index {i=}: "
                if len(targs) != 1 + len(arg_types):
                    error = f"{pfx}length {len(targs)} should include method selector and so have length 1 + {len(arg_types)}"
                    break

                if targs[0] != selector_if_needed:
                    error = f"{pfx}expected selector={selector_if_needed!r} at arg 0 but got {targs[0]!r}"
                    break

        assert not error, error

    def dry_run_on_sequence(
        self,
        algod: AlgodClient,
        method: Optional[str] = None,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        inputs: Optional[List[Sequence[PyTypes]]] = None,
        *,
        validation: bool = True,
        dryrun_accounts: List[DryRunAccountType] = [],
    ) -> List["DryRunInspector"]:
        """ARC-4 Compliant Dry Run
        When inputs aren't provided, you should INSTEAD SHOULD HAVE PROVIDED
        an `argument_strategy` upon construction.
        When inputs ARE provided, don't include the method selector as that
        is automatically generated.
        """
        # TODO: handle txn_params

        if inputs is None:
            inputs = self.generate_inputs(method)

        if validation:
            self.validate_inputs(method, inputs)

        return DryRunExecutor.dryrun_app_on_sequence(
            algod,
            self.program,
            inputs,
            abi_method_signature=self.method_signature(method),
            omit_method_selector=False,
            validation=validation,
            is_app_create=is_app_create,
            on_complete=on_complete,
            dryrun_accounts=dryrun_accounts,
        )
