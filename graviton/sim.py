from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, TypeVar

from algosdk.v2client.algod import AlgodClient

from graviton.blackbox import DryRunExecutor, DryRunTransactionParams as TxParams
from graviton.inspector import DryRunProperty as DRProp, DryRunInspector
from graviton.invariant import Invariant
from graviton.models import ExecutionMode, PyTypes

# TODO: this will encompass strategies, composed of
# hypothesis strategies as well as home grown ABIStrategy sub-types
InputStrategy = Iterable[Sequence[PyTypes]]


@dataclass(frozen=True)
class SimulationResults:
    succeeded: bool
    simulate_inspectors: List[DryRunInspector]
    identities_inspectors: Optional[List[DryRunInspector]] = None


class Simulation:
    """
    TODO: Slated to become the hypothesis plugin receptor.
    """

    def __init__(
        self,
        algod: AlgodClient,
        mode: ExecutionMode,
        simulate_teal: str,
        predicates: Dict[DRProp, Any],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: bool = True,
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
        txn_params: Optional[TxParams],
        verbose: bool = False,
        msg: str = "",
    ) -> SimulationResults:
        assert inputs, "must provide actual inputs to run against!"

        T = TypeVar("T")

        def listify(xs: Iterable[T]) -> List[T]:
            if isinstance(xs, list):
                return xs
            return list(xs)

        inputs_l = listify(inputs)
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
