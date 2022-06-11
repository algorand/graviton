"""
Inspired by Hypothesis' Strategies.

TODO: Leverage Hypothesis!
"""
from abc import ABC, abstractmethod
from collections import OrderedDict
import random
import string
from typing import Callable, Dict, List, Optional, Sequence, Union, cast

from algosdk import abi, encoding

PY_TYPES = Union[bool, int, Sequence, str, bytes]


class ABIStrategy(ABC):
    @abstractmethod
    def __init__(self, abi_instance: abi.ABIType, dynamic_length: Optional[int] = None):
        pass

    @abstractmethod
    def get(self) -> PY_TYPES:
        pass

    def get_many(self, n: int) -> List[PY_TYPES]:
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

    def get(self) -> PY_TYPES:
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

    def map(
        self,
        waterfall: Dict[abi.ABIType, Callable[..., PY_TYPES]],
        *args,
        **kwargs,
    ) -> PY_TYPES:
        for abi_type, call in waterfall.items():
            if isinstance(self.abi_type, abi_type):
                return call(*args, **kwargs)
        return waterfall["DEFAULT"](*args, **kwargs)

    def mutate_for_roundtrip(self, py_abi_instance: PY_TYPES) -> PY_TYPES:
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

        waterfall = OrderedDict(
            [
                (abi.UfixedType, not_implemented),
                (abi.BoolType, lambda x: not x),
                (abi.UintType, lambda x: (1 << self.abi_type.bit_size) - 1 - x),
                (
                    abi.ByteType,
                    lambda x: RandomABIStrategy(abi.UintType(8)).mutate_for_roundtrip(
                        x
                    ),
                ),
                (
                    abi.TupleType,
                    lambda x: [
                        RandomABIStrategy(child_type).mutate_for_roundtrip(x[i])
                        for i, child_type in enumerate(self.abi_type.child_types)
                    ],
                ),
                (
                    abi.ArrayStaticType,
                    lambda x: [
                        RandomABIStrategy(
                            self.abi_type.child_type
                        ).mutate_for_roundtrip(y)
                        for y in x
                    ],
                ),
                (abi.AddressType, address_logic),
                (
                    abi.ArrayDynamicType,
                    lambda x: [
                        RandomABIStrategy(
                            self.abi_type.child_type
                        ).mutate_for_roundtrip(y)
                        for y in x
                    ],
                ),
                (abi.StringType, lambda x: "".join(reversed(x))),
                ("DEFAULT", unexpected_type),
            ]
        )

        return self.map(waterfall, py_abi_instance)


class RandomABIStrategyHalfSized(RandomABIStrategy):
    def __init__(
        self,
        abi_instance: abi.ABIType,
        dynamic_length: Optional[int] = None,
    ):
        super().__init__(abi_instance, dynamic_length=dynamic_length)

    def get(self) -> PY_TYPES:
        full_random = super().get()

        if not isinstance(self.abi_type, abi.UintType):
            return full_random

        return full_random % (1 << (self.abi_type.bit_size // 2))
