from typing import List, Optional, Sequence, Type, cast

from algosdk import abi
from algosdk.v2client.algod import AlgodClient
from algosdk.transaction import OnComplete

from graviton.abi_strategy import ABIStrategy, RandomABIStrategy
from graviton.blackbox import DryRunExecutor, DryRunTransactionParams
from graviton.inspector import DryRunInspector, ExecutionMode
from graviton.models import DryRunAccountType, PyTypes


class ABIContractExecutor:
    """Execute an ABI Contract via Dry Run"""

    def __init__(
        self,
        teal: str,
        contract: str,
        argument_strategy: Optional[Type[ABIStrategy]] = RandomABIStrategy,
        num_dryruns: int = 1,
        *,
        handle_selector: bool = True,
    ):
        """
        teal - The program to run

        contract - ABI Contract JSON

        argument_strategy (optional) - strategy for generating arguments

        dry_runs (default=1) - the number of dry runs to run
            (generates different inputs each time)

        handle_selector (default=True) - usually we'll want to let
            `ABIContractExecutor.dryrun_on_sequence()`
            handle adding the method selector so this param
            should _probably_ be left True.
            But if set False: when providing `inputs`
            ensure that the 0'th argument for method calls is the selector.
            And when set True, when NOT providing `inputs`, the selector arg
            at index 0 will be added automatically.
        """
        self.program = teal
        self.contract: abi.Contract = abi.Contract.from_json(contract)
        self.argument_strategy: Optional[Type[ABIStrategy]] = argument_strategy
        self.num_dryruns = num_dryruns
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
            return [tuple() for _ in range(self.num_dryruns)]

        arg_types = self.argument_types(method)

        prefix = []
        if self.handle_selector and method:
            prefix = [self.contract.get_method_by_name(method).get_selector()]

        def gen_args():
            return tuple(
                prefix
                + [
                    cast(Type[ABIStrategy], self.argument_strategy)(arg_type).get()
                    for arg_type in arg_types
                ]
            )

        return [gen_args() for _ in range(self.num_dryruns)]

    def validate_inputs(self, method: Optional[str], inputs: List[Sequence[PyTypes]]):
        if not method:
            assert not any(
                inputs
            ), f"bare app calls require args to be empty but inputs={inputs}"
            return

        arg_types = self.argument_types(method)

        error = None
        if self.handle_selector:
            selector = self.contract.get_method_by_name(method).get_selector()

            for i, args in enumerate(inputs):
                targs = cast(tuple, args)
                if selector:
                    pfx = f"args at index {i=}: "
                    if len(targs) != 1 + len(arg_types):
                        error = f"{pfx}length {len(targs)} should include method selector and so have length 1 + {len(arg_types)}"
                        break

                    if targs[0] != selector:
                        error = f"{pfx}expected selector={selector!r} at arg 0 but got {targs[0]!r}"
                        break

        assert not error, error

    def dryrun_on_sequence(
        self,
        algod: AlgodClient,
        method: Optional[str] = None,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        inputs: Optional[List[Sequence[PyTypes]]] = None,
        *,
        validation: bool = True,
        dryrun_accounts: List[DryRunAccountType] = [],
    ) -> List[DryRunInspector]:
        """ARC-4 Compliant Dry Run
        When inputs aren't provided, you should INSTEAD SHOULD HAVE PROVIDED
        an `argument_strategy` upon construction.
        When inputs ARE provided, don't include the method selector as that
        is automatically generated.
        """

        if inputs is None:
            inputs = self.generate_inputs(method)

        if validation:
            self.validate_inputs(method, inputs)

        return list(
            cast(
                Sequence[DryRunInspector],
                DryRunExecutor(
                    algod,
                    ExecutionMode.Application,
                    self.program,
                    abi_method_signature=self.method_signature(method),
                    omit_method_selector=False,
                    validation=validation,
                )._run(
                    inputs,
                    txn_params=DryRunTransactionParams.for_app(
                        is_app_create=is_app_create,
                        on_complete=on_complete,
                        dryrun_accounts=dryrun_accounts,
                    ),
                ),
            )
        )
