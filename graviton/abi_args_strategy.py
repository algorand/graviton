from enum import Enum, auto
import random
from typing import List, Optional, Sequence, Type, cast

from algosdk import abi

from graviton.abi_strategy import ABIStrategy, RandomABIStrategy
from graviton.models import PyTypes


class ABIArgsMod(Enum):
    selector_byte_insert = auto()
    selector_byte_delete = auto()
    selector_byte_replace = auto()
    parameter_delete = auto()
    parameter_append = auto()


class ABIArgsStrategy:
    """
    TODO: refactor to comport with ABIStrategy + Hypothesis
    TODO: make this generic on the strategy type
    """

    append_args_type: abi.ABIType = abi.ByteType()

    def __init__(
        self,
        teal: str,
        contract: str,
        argument_strategy: Type[ABIStrategy] = RandomABIStrategy,
        *,
        num_dryruns: int = 1,
        handle_selector: bool = True,
        abi_args_mod: Optional[ABIArgsMod] = None,
    ):
        """
        teal - The program to run

        contract - ABI Contract JSON

        argument_strategy (default=RandomABIStrategy) - ABI strategy for generating arguments

        num_dry_runs (default=1) - the number of dry runs to run
            (generates different inputs each time)

        handle_selector (default=True) - usually we'll want to let
            `ABIContractExecutor.run_sequence()`
            handle adding the method selector so this param.
            But if set False: when providing `inputs`
            ensure that the 0'th argument for method calls is the selector.
            And when set True: when NOT providing `inputs`, the selector arg
            at index 0 will be added automatically.

        abi_args_mod (optional) - when desiring to mutate the args, provide an ABIArgsMod value
        """
        self.program = teal
        self.contract: abi.Contract = abi.Contract.from_json(contract)
        self.argument_strategy: Optional[Type[ABIStrategy]] = argument_strategy
        self.num_dryruns = num_dryruns
        self.handle_selector = handle_selector
        self.abi_args_mod = abi_args_mod

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

    def num_args(self) -> int:
        return len(self.argument_types())

    def generate(self, method: Optional[str]) -> List[Sequence[PyTypes]]:
        """
        Generates inputs appropriate for bare app calls and method calls
        according to available argument_strategy.
        """
        assert (
            self.argument_strategy
        ), "cannot generate inputs without an argument_strategy"

        mutating = self.abi_args_mod is not None

        if not (method or mutating):
            # bare calls receive no arguments
            return [tuple() for _ in range(self.num_dryruns)]

        arg_types = self.argument_types(method)

        prefix: List[bytes] = []
        if self.handle_selector and method:
            prefix = [self.contract.get_method_by_name(method).get_selector()]

        modify_selector = False
        if (action := self.abi_args_mod) in (
            ABIArgsMod.selector_byte_delete,
            ABIArgsMod.selector_byte_insert,
            ABIArgsMod.selector_byte_replace,
        ):
            assert (
                prefix
            ), f"{self.abi_args_mod=} which means we need to modify the selector, but we don't have one available to modify"
            modify_selector = True

        def selector_mod(prefix):
            assert isinstance(prefix, list) and len(prefix) <= 1
            if not (prefix and modify_selector):
                return prefix

            selector = prefix[0]
            idx = random.randint(0, 4)
            x, y = selector[:idx], selector[idx:]
            if action == ABIArgsMod.selector_byte_insert:
                selector = x + random.randbytes(1) + y
            elif action == ABIArgsMod.selector_byte_delete:
                selector = (x[:-1] + y) if x else y[:-1]
            else:
                assert (
                    action == ABIArgsMod.selector_byte_replace
                ), f"expected action={ABIArgsMod.selector_byte_replace} but got [{action}]"
                idx = random.randint(0, 3)
                selector = (
                    selector[:idx]
                    + bytes([(selector[idx] + 1) % 256])
                    + selector[idx + 1 :]
                )
            return [selector]

        def args_mod(args):
            if action not in (ABIArgsMod.parameter_append, ABIArgsMod.parameter_delete):
                return args

            if action == ABIArgsMod.parameter_delete:
                return args if not args else tuple(args[:-1])

            assert action == ABIArgsMod.parameter_append
            return args + (self.get(self.append_args_type),)

        def gen_args():
            # TODO: when incorporating hypothesis strategies, we'll need a more holistic
            # approach that looks at relationships amongst various args
            args = tuple(
                selector_mod(prefix) + [self.get(atype) for atype in arg_types]
            )
            return args_mod(args)

        return [gen_args() for _ in range(self.num_dryruns)]

    def get(self, gen_type: abi.ABIType) -> PyTypes:
        return cast(Type[ABIStrategy], self.argument_strategy)(gen_type).get()

    # TODO: should we delete this? I'm trying to limit the scope of where dry runs are called
    # def validate_inputs(self, method: Optional[str], inputs: List[Sequence[PyTypes]]):
    #     if not method:
    #         assert not any(
    #             inputs
    #         ), f"bare app calls require args to be empty but inputs={inputs}"
    #         return

    #     arg_types = self.argument_types(method)

    #     error = None
    #     if self.handle_selector:
    #         selector = self.contract.get_method_by_name(method).get_selector()

    #         for i, args in enumerate(inputs):
    #             targs = cast(tuple, args)
    #             if selector:
    #                 pfx = f"args at index {i=}: "
    #                 if len(targs) != 1 + len(arg_types):
    #                     error = f"{pfx}length {len(targs)} should include method selector and so have length 1 + {len(arg_types)}"
    #                     break

    #                 if targs[0] != selector:
    #                     error = f"{pfx}expected selector={selector!r} at arg 0 but got {targs[0]!r}"
    #                     break

    #     assert not error, error

    # TODO: should we delete this? I'm trying to limit the scope of where dry runs are called
    # def run_sequence(
    #     self,
    #     algod: AlgodClient,
    #     method: Optional[str] = None,
    #     is_app_create: bool = False,
    #     on_complete: OnComplete = OnComplete.NoOpOC,
    #     inputs: Optional[List[Sequence[PyTypes]]] = None,
    #     *,
    #     validation: bool = True,
    #     dryrun_accounts: List[DryRunAccountType] = [],
    # ) -> List[DryRunInspector]:
    #     """ARC-4 Compliant Dry Run
    #     When inputs aren't provided, you should INSTEAD SHOULD HAVE PROVIDED
    #     an `argument_strategy` upon construction.
    #     When inputs ARE provided, don't include the method selector as that
    #     is automatically generated.
    #     """

    #     if inputs is None:
    #         inputs = self.generate_inputs(method)

    #     if validation:
    #         self.validate_inputs(method, inputs)

    #     return list(
    #         cast(
    #             Sequence[DryRunInspector],
    #             DryRunExecutor(
    #                 algod,
    #                 ExecutionMode.Application,
    #                 self.program,
    #                 abi_method_signature=self.method_signature(method),
    #                 omit_method_selector=False,
    #                 validation=validation,
    #             )._run(
    #                 inputs,
    #                 txn_params=DryRunTransactionParams.for_app(
    #                     is_app_create=is_app_create,
    #                     on_complete=on_complete,
    #                     dryrun_accounts=dryrun_accounts,
    #                 ),
    #             ),
    #         )
    #     )
