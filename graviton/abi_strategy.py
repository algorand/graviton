"""
Inspired by Hypothesis' Strategies.

TODO: Leverage Hypothesis!
"""
from abc import ABC, abstractmethod
from enum import Enum, auto
import random
import string
from typing import List, Optional, Sequence, Type, cast

from algosdk import abi, encoding


from graviton.models import PyTypes


class ABIStrategy(ABC):
    """
    TODO: when incorporating hypothesis strategies, we'll need a more holistic
    approach that looks at relationships amongst various args.
    Current approach only looks at each argument as a completely independent entity.
    """

    @abstractmethod
    def __init__(self, abi_instance: abi.ABIType, dynamic_length: Optional[int] = None):
        pass

    @abstractmethod
    def get(self) -> PyTypes:
        pass

    def get_many(self, n: int) -> List[PyTypes]:
        return [self.get() for _ in range(n)]


class RandomABIStrategy(ABIStrategy):
    DEFAULT_DYNAMIC_ARRAY_LENGTH = 3
    STRING_CHARS = string.digits + string.ascii_letters + string.punctuation

    seeded_randomness: bool = False
    random_seed: int

    @classmethod
    def seed_randomness(cls, random_seed: int = 42):
        """
        If you never call this function, there won't be a specific random seed.
        """
        if cls.seeded_randomness:
            print(f"already seeded with seed {cls.random_seed}")
            return

        cls.random_seed = random_seed
        random.seed(cls.random_seed)

        cls.seeded_randomness = True

    def __init__(self, abi_instance: abi.ABIType, dynamic_length: Optional[int] = None):
        assert isinstance(
            abi_instance, abi.ABIType
        ), f"expected abi_type but got {abi_instance} of type {type(abi_instance)}"

        assert dynamic_length is None or isinstance(
            dynamic_length, int
        ), f"expected dynamic_length to be an int but was given {type(dynamic_length)}"

        self.abi_type: abi.ABIType = abi_instance
        self.dynamic_length: Optional[int] = dynamic_length

    def get(self) -> PyTypes:
        if isinstance(self.abi_type, abi.UfixedType):
            raise NotImplementedError(
                f"Currently cannot get a random sample for {self.abi_type}"
            )

        if isinstance(self.abi_type, abi.BoolType):
            return random.choice([True, False])

        if isinstance(self.abi_type, abi.UintType):
            return random.randint(0, (1 << self.abi_type.bit_size) - 1)

        if isinstance(self.abi_type, abi.ByteType):
            return RandomABIStrategy(abi.UintType(8)).get()

        if isinstance(self.abi_type, abi.TupleType):
            return [
                RandomABIStrategy(child_type).get()
                for child_type in self.abi_type.child_types
            ]

        if isinstance(self.abi_type, abi.ArrayStaticType):
            return [
                RandomABIStrategy(self.abi_type.child_type).get()
                for _ in range(self.abi_type.static_length)
            ]

        if isinstance(self.abi_type, abi.AddressType):
            return encoding.encode_address(
                bytearray(
                    cast(
                        List[int],
                        RandomABIStrategy(
                            abi.ArrayStaticType(
                                abi.ByteType(), self.abi_type.byte_len()
                            )
                        ).get(),
                    )
                )
            )

        dynamic_range = range(
            self.DEFAULT_DYNAMIC_ARRAY_LENGTH
            if self.dynamic_length is None
            else self.dynamic_length
        )
        if isinstance(self.abi_type, abi.ArrayDynamicType):
            return [
                RandomABIStrategy(self.abi_type.child_type).get() for _ in dynamic_range
            ]

        if isinstance(self.abi_type, abi.StringType):
            return "".join(random.choice(self.STRING_CHARS) for _ in dynamic_range)

        raise ValueError(f"Unexpected abi_type {self.abi_type}")

    def mutate_for_roundtrip(self, py_abi_instance: PyTypes) -> PyTypes:
        def not_implemented(_):
            raise NotImplementedError(f"Currently cannot handle type {self.abi_type}")

        def unexpected_type(_):
            raise ValueError(f"Unexpected abi_type {self.abi_type}")

        def address_logic(x):
            y = encoding.decode_address(x)
            return encoding.encode_address(
                bytearray(
                    RandomABIStrategy(
                        abi.ArrayStaticType(abi.ByteType(), len(y))
                    ).mutate_for_roundtrip(y)
                )
            )

        if isinstance(self.abi_type, abi.UfixedType):
            return not_implemented(py_abi_instance)
        elif isinstance(self.abi_type, abi.BoolType):
            return not py_abi_instance
        elif isinstance(self.abi_type, abi.UintType):
            assert isinstance(py_abi_instance, int)
            return (1 << self.abi_type.bit_size) - 1 - py_abi_instance
        elif isinstance(self.abi_type, abi.ByteType):
            return RandomABIStrategy(abi.UintType(8)).mutate_for_roundtrip(
                py_abi_instance
            )
        elif isinstance(self.abi_type, abi.TupleType):
            assert isinstance(py_abi_instance, Sequence)
            return [
                RandomABIStrategy(child_type).mutate_for_roundtrip(py_abi_instance[i])
                for i, child_type in enumerate(self.abi_type.child_types)
            ]
        elif isinstance(self.abi_type, abi.ArrayStaticType):
            assert isinstance(py_abi_instance, Sequence)
            return [
                RandomABIStrategy(self.abi_type.child_type).mutate_for_roundtrip(y)
                for y in py_abi_instance
            ]
        elif isinstance(self.abi_type, abi.AddressType):
            return address_logic(py_abi_instance)
        elif isinstance(self.abi_type, abi.ArrayDynamicType):
            assert isinstance(py_abi_instance, Sequence)
            return [
                RandomABIStrategy(self.abi_type.child_type).mutate_for_roundtrip(y)
                for y in py_abi_instance
            ]
        elif isinstance(self.abi_type, abi.StringType):
            assert isinstance(py_abi_instance, str)
            return "".join(reversed(py_abi_instance))
        else:
            return unexpected_type(py_abi_instance)


class RandomABIStrategyHalfSized(RandomABIStrategy):
    """
    This strategy only generates data that is half the size that _ought_ to be possible.
    This is useful in the case that operations involving the generated arguments
    could overflow due to multiplication.

    Since this only makes sense for `abi.UintType`, it degenerates to the standard
    `RandomABIStrategy` for other types.
    """

    def __init__(
        self,
        abi_instance: abi.ABIType,
        dynamic_length: Optional[int] = None,
    ):
        super().__init__(abi_instance, dynamic_length=dynamic_length)

    def get(self) -> PyTypes:
        full_random = super().get()

        if not isinstance(self.abi_type, abi.UintType):
            return full_random

        return cast(int, full_random) % (
            1 << (cast(abi.UintType, self.abi_type).bit_size // 2)
        )


class ABIArgsMod(Enum):
    selector_byte_insert = auto()
    selector_byte_delete = auto()
    selector_byte_replace = auto()
    parameter_delete = auto()
    parameter_append = auto()


class ABIMethodCallStrategy:
    """
    TODO: refactor to comport with ABIStrategy + Hypothesis
    TODO: make this generic on the strategy type
    """

    append_args_type: abi.ABIType = abi.ByteType()

    def __init__(
        self,
        teal: str,
        contract: str,
        method: Optional[str],
        argument_strategy: Type[ABIStrategy] = RandomABIStrategy,
        *,
        num_dryruns: int = 1,
        handle_selector: bool = True,
        abi_args_mod: Optional[ABIArgsMod] = None,
    ):
        """
        teal - The program to run

        contract - ABI Contract JSON

        method - The method for calling (`None` for bare app call)

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
        self.method: Optional[str] = method
        self.argument_strategy: Optional[Type[ABIStrategy]] = argument_strategy
        self.num_dryruns = num_dryruns
        self.handle_selector = handle_selector
        self.abi_args_mod = abi_args_mod

        assert self.method is None or self.method_signature()

    def abi_method(self) -> abi.Method:
        assert self.method, "cannot get abi.Method for bare app call"

        return self.contract.get_method_by_name(self.method)

    def method_signature(self) -> Optional[str]:
        """Returns None, for a bare app call (method=None signals this)"""
        if self.method is None:
            return None

        return self.abi_method().get_signature()

    def method_selector(self) -> bytes:
        assert self.method, "cannot get method_selector for bare app call"

        return self.abi_method().get_selector()

    def argument_types(self) -> List[abi.ABIType]:
        """
        Argument types (excluding selector)
        """
        if self.method is None:
            return []

        return [cast(abi.ABIType, arg.type) for arg in self.abi_method().args]

    def num_args(self) -> int:
        return len(self.argument_types())

    def generate(self) -> List[Sequence[PyTypes]]:
        """
        Generates inputs appropriate for bare app calls and method calls
        according to available argument_strategy.
        """
        assert (
            self.argument_strategy
        ), "cannot generate inputs without an argument_strategy"

        mutating = self.abi_args_mod is not None

        if not (self.method or mutating):
            # bare calls receive no arguments
            return [tuple() for _ in range(self.num_dryruns)]

        arg_types = self.argument_types()

        prefix: List[bytes] = []
        if self.handle_selector and self.method:
            prefix = [self.method_selector()]

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
