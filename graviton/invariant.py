from inspect import getsource, signature
from typing import cast, Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from graviton.abi_strategy import PY_TYPES
from graviton.blackbox import (
    DryRunInspector,
    DryRunProperty,
    ExecutionMode,
    mode_has_property,
)


INVARIANT_TYPE = Union[
    PY_TYPES,
    Dict[Sequence[PY_TYPES], PY_TYPES],
    Callable[[PY_TYPES], PY_TYPES],
    Callable[[PY_TYPES], bool],
]


class Invariant:
    """Enable asserting invariants on a sequence of dry run executions"""

    def __init__(
        self,
        predicate: INVARIANT_TYPE,
        enforce: bool = False,
        name: Optional[str] = None,
    ):
        self.definition = predicate
        self.predicate, self._expected = self.prepare_predicate(predicate)
        self.enforce = enforce
        self.name = name

    def __repr__(self):
        return f"Invariant({self.definition})"[:100]

    def __call__(self, args: Sequence[PY_TYPES], actual: PY_TYPES) -> Tuple[bool, str]:
        invariant = self.predicate(args, actual)
        msg = ""
        if not invariant:
            expected = self.expected(args)
            if callable(expected):
                expected = getsource(expected)
            msg = f"Invariant for '{self.name}' failed for for args {args!r}: actual is [{actual!r}] BUT expected [{expected!r}]"
            if self.enforce:
                assert invariant, msg

        return invariant, msg

    def expected(self, args: Sequence[PY_TYPES]) -> PY_TYPES:
        return self._expected(args)

    def validates(
        self,
        dr_property: DryRunProperty,
        inspectors: List[DryRunInspector],
        *,
        msg: str = "",
    ):
        assert isinstance(
            dr_property, DryRunProperty
        ), f"invariants types must be DryRunProperty's but got [{dr_property}] which is a {type(dr_property)}"

        for i, inspector in enumerate(inspectors):
            actual = inspector.dig(dr_property)
            ok, fail_msg = self(inspector.args, actual)
            if msg:
                fail_msg += f". invariant provided message:{msg}"
            assert ok, inspector.report(msg=fail_msg, row=i + 1)

    @classmethod
    def prepare_predicate(
        cls,
        predicate: INVARIANT_TYPE,
    ) -> Tuple[Callable[[Sequence[PY_TYPES], PY_TYPES], bool], Callable]:
        # returns
        # * Callable[[Sequence[PY_TYPES], PY_TYPES], bool]
        # * Callable[[Sequence[PY_TYPES]], PY_TYPES]
        if isinstance(predicate, dict):
            d_predicate = cast(Dict[PY_TYPES, PY_TYPES], predicate)
            return (
                lambda args, actual: d_predicate[args] == actual,
                lambda args: d_predicate[args],
            )

        # predicate = cast(Callable, predicate)
        # returns
        # * Callable[[Any], PY_TYPES], bool]
        # * Callable[[Any], PY_TYPES]
        if not callable(predicate):
            # constant function in this case:
            return lambda _, actual: predicate == actual, lambda _: predicate

        try:
            sig = signature(predicate)
        except Exception as e:
            raise Exception(
                f"callable predicate {predicate} must have a signature"
            ) from e

        N = len(sig.parameters)
        assert N in (1, 2), f"predicate has the wrong number of paramters {N}"

        if N == 2:
            c2_predicate = cast(
                Callable[[Sequence[PY_TYPES], PY_TYPES], bool], predicate
            )
            # returns
            # * Callable[[Sequence[PY_TYPES], PY_TYPES], bool]
            # * Callable[Any, Callable[[Sequence[PY_TYPES], PY_TYPES], bool]]
            return c2_predicate, lambda _: c2_predicate

        # N == 1:
        c1_predicate = cast(Callable[[Sequence[PY_TYPES]], bool], predicate)
        # returns
        # * Callable[[Sequence[PY_TYPES]], bool]
        # * Callable[[Sequence[PY_TYPES]], PY_TYPES]
        return lambda args, actual: c1_predicate(
            args
        ) == actual, lambda args: c1_predicate(args)

    @classmethod
    def inputs_and_invariants(
        cls,
        scenario: Dict[str, Any],
        mode: ExecutionMode,
        raw_predicates: bool = False,
    ) -> Tuple[List[Sequence[Union[str, int]]], Dict[DryRunProperty, Any]]:
        """
        TODO: Do we really need this, or does this just overcomplicate?

        Validate that a Blackbox Test Scenario has been properly constructed, and return back
        its components which consist of **inputs** and _optional_ **invariants**.

        A scenario should adhere to the following schema:
        ```
        {
            "inputs":       List[Tuple[Union[str, int], ...]],
            "invariants":   Dict[DryRuninvariantType, ...an invariant...]
        }

        Each invariant is a map from a _dryrun property_ to assert about
        to the actual invariant. Actual invariants can be:
        * simple python types - these are useful in the case of _constant_ invariants.
            For example, if you want to assert that the `maxStackHeight` is 3, just use `3`.
        * dictionaries of type Dict[Tuple, Any] - these are useful when you just want to assert
            a discrete set of input-output pairs.
            For example, if you have 4 inputs that you want to assert are being squared,
            you could use `{(2,): 4, (7,): 49, (13,): 169, (11,): 121}`
        * functions which take a single variable. These are useful when you have a python "simulator"
            for the invariant.
            In the square example you could use `lambda args: args[0]**2`
        * functions which take _two_ variables. These are useful when your invariant is more
            subtle that out-and-out equality. For example, suppose you want to assert that the
            `cost` of the dry run is `2*n` plus/minus 5 where `n` is the first arg of the input. Then
            you could use `lambda args, actual: 2*args[0] - 5 <= actual <= 2*args[0] + 5`
        ```
        """
        assert isinstance(
            scenario, dict
        ), f"a Blackbox Scenario should be a dict but got a {type(scenario)}"

        inputs = cast(List[Sequence[Union[str, int]]], scenario.get("inputs"))
        assert (
            inputs
            and isinstance(inputs, list)
            and all(isinstance(args, tuple) for args in inputs)
        ), "need a list of inputs with at least one args and all args must be tuples"

        predicates = cast(Dict[DryRunProperty, Any], scenario.get("invariants", {}))
        if predicates:
            assert isinstance(predicates, dict), "invariants must be a dict"

        return inputs, predicates if raw_predicates else cls.as_invariants(
            predicates, mode
        )

    @classmethod
    def as_invariants(
        cls,
        predicates: Dict[DryRunProperty, Any],
        mode: ExecutionMode = ExecutionMode.Application,
    ) -> Dict[DryRunProperty, "Invariant"]:
        invariants: Dict[DryRunProperty, Any] = {}

        for key, predicate in predicates.items():
            assert isinstance(key, DryRunProperty) and mode_has_property(
                mode, key
            ), f"each key must be a DryRunProperty's appropriate to {mode}. This is not the case for key {key}"
            invariants[key] = Invariant(predicate, name=str(key))
        return invariants
