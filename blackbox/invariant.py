from inspect import signature
from typing import Any, Callable, Dict, List, Tuple, Union

from ..blackbox.blackbox import (
    DryRunInspector,
    DryRunProperty,
    ExecutionMode,
    mode_has_property,
)


class Invariant:
    """Enable asserting invariants on a sequence of dry run executions"""

    def __init__(
        self,
        predicate: Union[Dict[Tuple, Union[str, int]], Callable],
        enforce: bool = False,
        name: str = None,
    ):
        self.definition = predicate
        self.predicate, self._expected = self.prepare_predicate(predicate)
        self.enforce = enforce
        self.name = name

    def __repr__(self):
        return f"Invariant({self.definition})"[:100]

    def __call__(self, args: list, actual: Union[str, int]) -> Tuple[bool, str]:
        invariant = self.predicate(args, actual)
        msg = ""
        if not invariant:
            msg = f"Invariant for '{self.name}' failed for for args {args}: actual is [{actual}] BUT expected [{self.expected(args)}]"
            if self.enforce:
                assert invariant, msg

        return invariant, msg

    def expected(self, args: list) -> Union[str, int]:
        return self._expected(args)

    def validates(
        self,
        property: DryRunProperty,
        inputs: List[list],
        inspectors: List[DryRunInspector],
    ):
        N = len(inputs)
        assert N == len(
            inspectors
        ), f"inputs (len={N}) and dryrun responses (len={len(inspectors)}) must have the same length"

        assert isinstance(
            property, DryRunProperty
        ), f"invariants types must be DryRunProperty's but got [{property}] which is a {type(property)}"

        for i, args in enumerate(inputs):
            res = inspectors[i]
            actual = res.dig(property)
            ok, msg = self(args, actual)
            assert ok, res.report(args, msg, row=i + 1)

    @classmethod
    def prepare_predicate(cls, predicate):
        if isinstance(predicate, dict):
            return (
                lambda args, actual: predicate[args] == actual,
                lambda args: predicate[args],
            )

        if not isinstance(predicate, Callable):
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
            return predicate, lambda _: predicate

        # N == 1:
        return lambda args, actual: predicate(args) == actual, lambda args: predicate(
            args
        )

    @classmethod
    def inputs_and_invariants(
        cls,
        scenario: Dict[str, Union[list, dict]],
        mode: ExecutionMode,
        raw_predicates: bool = False,
    ) -> Tuple[List[tuple], Dict[DryRunProperty, Any]]:
        """
        Validate that a Blackbox Test Scenario has been properly constructed, and return back
        its components which consist of **inputs** and _optional_ **invariants**.

        A scenario should adhere to the following schema:
        ```
        {
            "inputs":       List[Tuple[Union[str, int], ...]],
            "invariants":   Dict[DryRuninvariantType, ...an invariant...]
        }

        Each invariants is a map from a _dryrun property_ to assert about
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

        inputs = scenario.get("inputs")
        # TODO: we can be more flexible here and allow arbitrary iterable `args`. Because
        # invariants are allowed to be dicts, and therefore each `args` needs to be
        # hashable in that case, we are restricting to tuples currently.
        # However, this function could be friendlier and just _convert_ each of the
        # `args` to a tuple, thus eliminating any downstream issues.
        assert (
            inputs
            and isinstance(inputs, list)
            and all(isinstance(args, tuple) for args in inputs)
        ), "need a list of inputs with at least one args and all args must be tuples"

        invariants = {}
        predicates = scenario.get("invariants", {})
        if predicates:
            assert isinstance(predicates, dict), f"invariants must be a dict"

            for key, predicate in predicates.items():
                assert isinstance(key, DryRunProperty) and mode_has_property(
                    mode, key
                ), f"each key must be a DryRunProperty's appropriate to {mode}. This is not the case for key {key}"
                invariants[key] = Invariant(predicate, name=key)

        return inputs, predicates if raw_predicates else invariants
