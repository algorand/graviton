from enum import Enum
from inspect import getsource, signature
from typing import cast, Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from graviton.abi_strategy import PyTypes
from graviton.blackbox import (
    DryRunInspector,
    DryRunProperty,
    ExecutionMode,
    mode_has_property,
)


class PredicateKind(Enum):
    Constant = "constant"
    CaseMap = "case map"
    ExactMatch = "exact match"
    RangeMatch = "range match"
    IdenticalPair = "identical"


INVARIANT_TYPE = Union[
    # sentinel invariant, eg:
    # Predicate.IdenticalPair
    PredicateKind,
    # dict invariant, eg:
    # {(0,): 0**2, (1,): 1**2}
    Dict[Tuple[PyTypes, ...], PyTypes],
    # constant invariant, eg:
    # 42
    PyTypes,
    # range match invariant, eg:
    # lambda args, actual: -17 <= f(args[0]) - actual <= 17
    Callable[[Tuple[PyTypes, ...], PyTypes], bool],
    # exact match invariant, eg:
    # lambda args: f(args[0])
    Callable[[Tuple[PyTypes, ...]], PyTypes],
]


def get_kind(predicate: INVARIANT_TYPE) -> PredicateKind:
    if isinstance(predicate, PredicateKind):
        # sentinel predicate
        return predicate

    if isinstance(predicate, dict):
        # mapping predicate of type Dict[Tuple[PyTypes, ...], PyTypes]
        return PredicateKind.CaseMap

    if not callable(predicate):
        return PredicateKind.Constant

    try:
        sig = signature(predicate)
    except Exception as e:
        raise Exception(f"callable predicate {predicate} must have a signature") from e

    N = len(sig.parameters)
    assert N in (1, 2), f"predicate has the wrong number of paramters {N}"

    if N == 2:
        # range match invariant of type Callable[[Tuple[PyTypes, ...], PyTypes], bool]
        return PredicateKind.RangeMatch

    # exact match invariant of type Callable[[Tuple[PyTypes, ...]], PyTypes]
    return PredicateKind.ExactMatch


class Invariant:
    """Enable asserting invariants on a sequence of dry run executions"""

    def __init__(
        self,
        predicate: INVARIANT_TYPE,
        enforce: bool = False,
        name: Optional[str] = None,
    ):
        self.definition = predicate
        self.predicate_kind: PredicateKind
        self.predicate: Callable
        self._expected: Callable
        self.predicate_kind, self.predicate, self._expected = self.prepare_predicate(
            predicate
        )
        self.enforce = enforce
        self.name = name

    def __repr__(self):
        defn = self.definition
        if callable(defn):
            defn = getsource(defn)

        return f"Invariant({defn})"

    def __call__(
        self,
        args: Sequence[PyTypes],
        actual: PyTypes,
        **kwargs,
    ) -> Tuple[bool, str]:
        has_external_expected: bool = False
        if kwargs and (ee_key := "external_expected") in kwargs:
            has_external_expected = True
            external_expected: Optional[PyTypes] = kwargs[ee_key]
        invariant = (
            self.predicate(args, actual, external_expected)
            if has_external_expected
            else self.predicate(args, actual)
        )

        msg = ""
        if not invariant:
            expected = (
                self.expected(actual, external_expected)
                if has_external_expected
                else self.expected(args)
            )
            prefix = f"Invariant of {self.predicate_kind} for '{self.name}' failed for for args {args!r}: "
            if self.predicate_kind == PredicateKind.IdenticalPair:
                msg = prefix + f"(actual, expected) = {expected!r}"
            else:
                msg = prefix + f"actual is [{actual!r}] BUT expected [{expected!r}]"

            if self.enforce:
                assert invariant, msg

        return invariant, msg

    def expected(self, x: Any, y: Any = None) -> PyTypes:
        return (
            self._expected(x, y)
            if self.predicate_kind == PredicateKind.IdenticalPair or y is not None
            else self._expected(x)
        )

    def validates(
        self,
        dr_property: DryRunProperty,
        inspectors: Sequence[DryRunInspector],
        *,
        identities: Optional[Sequence[DryRunInspector]] = None,
        msg: str = "",
    ):
        assert isinstance(
            dr_property, DryRunProperty
        ), f"invariants types must be DryRunProperty's but got [{dr_property}] which is a {type(dr_property)}"

        if identities:
            assert (
                self.predicate_kind == PredicateKind.IdenticalPair
            ), f"Unhandled PredicateKind {self.predicate_kind}"
            for i, inspector in enumerate(inspectors):
                identity = identities[i]

                assert (
                    inspector.abi_type == identity.abi_type
                ), f"IdenticalPair predicates should have the same abi_type but {inspector.abi_type=} V. {identity.abi_type=}"

                assert (
                    inspector.abi_params_or_args() == identity.abi_params_or_args()
                ), f"IdenticalPair predicates expects the same argments but they aren't: {inspector.abi_params_or_args()=} V. {identity.abi_params_or_args()=}"
                expected = identity.dig(dr_property)
                actual = inspector.dig(dr_property)
                ok, fail_msg = self(inspector.args, actual, external_expected=expected)
                if msg:
                    fail_msg += f". invariant provided message:{msg}"
                assert ok, inspector.report(msg=fail_msg, row=i + 1)

            return

        for i, inspector in enumerate(inspectors):
            actual = inspector.dig(dr_property)
            ok, fail_msg = self(inspector.args, actual)
            if msg:
                fail_msg += f". invariant provided message:{msg}"
            assert ok, inspector.report(msg=fail_msg, row=i + 1)

    @classmethod
    def prepare_predicate(
        cls, predicate: INVARIANT_TYPE
    ) -> Tuple[PredicateKind, Callable, Callable]:
        kind = get_kind(predicate)

        def get_return(f, g):
            return kind, f, g

        if kind == PredicateKind.IdenticalPair:
            # equality between 2 inspectors
            # returns
            # * Callable[[Any, PyTypes, PyTypes], bool]
            # * Callable[[PyTypes, PyTypes], Tuple[PyTypes, PyTypes]]
            return get_return(
                lambda _, actual, expected: actual == expected,
                lambda actual, expected: (actual, expected),
            )

        if kind == PredicateKind.CaseMap:
            # returns
            # * Callable[[Tuple[PyTypes, ...], PyTypes], bool]
            # * Callable[[Tuple[PyTypes, ...]], PyTypes]
            d_predicate = cast(Dict[Tuple[PyTypes], PyTypes], predicate)
            return get_return(
                lambda args, actual: d_predicate[args] == actual,
                lambda args: d_predicate[args],
            )

        if kind == PredicateKind.Constant:
            # returns
            # * Callable[[Any, PyTypes], bool]
            # * Callable[[Any], PyTypes]
            # constant function in this case:
            a_const = predicate
            return get_return(lambda _, actual: a_const == actual, lambda _: a_const)

        if kind == PredicateKind.RangeMatch:
            # N == 2 args:
            # returns
            # * Callable[[Tuple[PyTypes, ...], PyTypes], bool]
            # * Callable[[Tuple[PyTypes, ...]], str]
            c2_predicate = cast(
                Callable[[Tuple[PyTypes, ...], PyTypes], bool], predicate
            )
            return get_return(c2_predicate, lambda args: f"RangeMatch({args=})")

        if kind == PredicateKind.ExactMatch:
            # N == 1 args:
            # returns
            # * Callable[[Tuple[PyTypes, ...]], bool]
            # * Callable[[Tuple[PyTypes, ...]], PyTypes]
            c1_predicate = cast(Callable[[Tuple[PyTypes, ...]], PyTypes], predicate)
            return get_return(
                lambda args, actual: c1_predicate(args) == actual, c1_predicate
            )

        raise ValueError("Unhanlded PredicateKind {kind} for predicate {predicate}")

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

    @classmethod
    def full_validation(
        cls,
        predicates: Dict[DryRunProperty, Any],
        inspectors: Sequence[DryRunInspector],
        *,
        identities: Optional[Sequence[DryRunInspector]] = None,
        msg: str = "",
    ) -> None:
        invariants = Invariant.as_invariants(predicates)

        for dr_prop, invariant in invariants.items():
            invariant.validates(
                dr_prop, inspectors=inspectors, identities=identities, msg=msg
            )
