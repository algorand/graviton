from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, TypeVar, Union, cast

from algosdk.v2client.algod import AlgodClient

from graviton.abi_strategy import CallStrategy
from graviton.blackbox import DryRunExecutor, DryRunTransactionParams as TxParams
from graviton.inspector import DryRunProperty as DRProp, DryRunInspector
from graviton.invariant import Invariant
from graviton.models import ExecutionMode, PyTypes

# TODO: this will encompass strategies, composed of
# hypothesis strategies as well as home grown ABIStrategy sub-types
InputStrategy = Union[Iterable[Sequence[PyTypes]], CallStrategy]


@dataclass(frozen=True)
class SimulationResults:
    succeeded: bool
    simulate_inspectors: List[DryRunInspector]
    identities_inspectors: Optional[List[DryRunInspector]] = None


class Simulation:
    """
    Simulation ~ (Teal logic for execution) + (predicates that must be satisfied)

    TODO: Slated to become the hypothesis plugin receptor.
    TODO: Add some real comments (cf. Issue #51)
    """

    def __init__(
        self,
        algod: AlgodClient,
        mode: ExecutionMode,
        simulate_teal: str,
        predicates: Dict[DRProp, Any],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: bool = False,
        validation: bool = True,
        identities_teal: Optional[str] = None,
    ):
        self.simulate_dre: DryRunExecutor = DryRunExecutor(
            algod,
            mode,
            simulate_teal,
            abi_method_signature=abi_method_signature,
            omit_method_selector=omit_method_selector,
            validation=validation,
        )
        self.identities_dre: Optional[DryRunExecutor] = None
        if identities_teal:
            self.identities_dre = DryRunExecutor(
                algod,
                mode,
                identities_teal,
                abi_method_signature=abi_method_signature,
                omit_method_selector=omit_method_selector,
                validation=validation,
            )
        self.predicates: Dict[DRProp, Any] = predicates

        assert self.predicates, "must provide actual predicates to assert with!"

    def run_and_assert(
        self,
        inputs: InputStrategy,
        *,
        txn_params: Optional[TxParams] = None,
        verbose: bool = False,
        msg: str = "",
    ) -> SimulationResults:
        """
        run_and_assert: simulation + InputStrategy → SUCCESS or FAILURE

        TODO: Add some real comments (cf. Issue #51)
        """
        assert inputs, "must provide actual inputs to run against!"

        T = TypeVar("T")

        def listify(xs: Iterable[T]) -> List[T]:
            if isinstance(xs, list):
                return xs
            return list(xs)

        inputs_iter: Iterable[PyTypes]
        if isinstance(inputs, CallStrategy):
            method = m.name if (m := self.simulate_dre.method) else None
            inputs_iter = inputs.generate_inputs(method)
        else:
            inputs_iter = cast(Iterable[Sequence[PyTypes]], inputs)

        inputs_l = listify(inputs_iter)
        simulate_inspectors = listify(
            self.simulate_dre.run_sequence(
                inputs_l, txn_params=txn_params, verbose=verbose
            )
        )
        identities_inspectors = None
        if self.identities_dre:
            identities_inspectors = listify(
                self.identities_dre.run_sequence(
                    inputs_l, txn_params=txn_params, verbose=verbose
                )
            )

        Invariant.full_validation(
            self.predicates,
            simulate_inspectors,
            identities=identities_inspectors,
            msg=msg,
        )

        return SimulationResults(True, simulate_inspectors, identities_inspectors)
