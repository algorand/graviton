"""
Inspired by Hypothesis' Strategies.

TODO: Leverage Hypothesis!
"""
import random
import string
from typing import List, Optional, Union, cast

from algosdk import abi, encoding
from numpy import isin


class ABIStrategy:
    DEFAULT_DYNAMIC_ARRAY_LENGTH = 3

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

    def get_random(self) -> Union[bool, int, list, str, bytes]:
        if isinstance(self.abi_type, abi.UfixedType):
            raise NotImplementedError(
                f"Currently cannot get a random sample for {self.abi_type}"
            )

        if isinstance(self.abi_type, abi.BoolType):
            return random.choice([True, False])

        if isinstance(self.abi_type, abi.UintType):
            return random.randint(0, (1 << self.abi_type.bit_size) - 1)

        if isinstance(self.abi_type, abi.ByteType):
            return ABIStrategy(abi.UintType(8)).get_random()

        if isinstance(self.abi_type, abi.TupleType):
            return [
                ABIStrategy(child_type).get_random()
                for child_type in self.abi_type.child_types
            ]

        if isinstance(self.abi_type, abi.ArrayStaticType):
            return [
                ABIStrategy(self.abi_type.child_type).get_random()
                for _ in range(self.abi_type.static_length)
            ]

        if isinstance(self.abi_type, abi.AddressType):
            return encoding.encode_address(
                bytearray(
                    cast(
                        List[int],
                        ABIStrategy(
                            abi.ArrayStaticType(
                                abi.ByteType(), self.abi_type.byte_len()
                            )
                        ).get_random(),
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
                ABIStrategy(self.abi_type.child_type).get_random()
                for _ in dynamic_range
            ]

        if isinstance(self.abi_type, abi.StringType):
            return "".join(random.choice(string.printable) for _ in dynamic_range)

        raise ValueError(f"Unexpected abi_type {self.abi_type}")
