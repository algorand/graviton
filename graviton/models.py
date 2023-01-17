from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Sequence, Union

from algosdk.encoding import encode_address
from algosdk.transaction import OnComplete
from algosdk.v2client.models.account import Account
from algosdk.v2client.models.teal_key_value import TealKeyValue

ZERO_ADDRESS = encode_address(bytes(32))

ArgType = Union[bytes, str]
DryRunAccountType = Union[str, Account]
Stringy = Union[str, bytes]
PyTypes = Union[bool, int, Sequence, Stringy]


class ExecutionMode(Enum):
    Signature = auto()
    Application = auto()


def get_run_mode(app):
    run_mode = "lsig"
    if app is not None:
        on_complete = (
            app.get("on_complete") if isinstance(app, dict) else app.on_complete
        )
        run_mode = "clearp" if on_complete == OnComplete.ClearStateOC else "approv"
    return run_mode


@dataclass
class LSig:
    """Logic Sig program parameters"""

    args: Optional[List[ArgType]] = None


@dataclass
class App:
    """Application program parameters"""

    creator: str = ZERO_ADDRESS
    round: Optional[int] = None
    app_idx: int = 0
    on_complete: int = 0
    args: Optional[List[ArgType]] = None
    accounts: Optional[List[DryRunAccountType]] = None
    global_state: Optional[List[TealKeyValue]] = None

    @classmethod
    def factory(cls, **kwargs) -> "App":
        app = cls()
        for key, val in kwargs.items():
            if hasattr(app, key) and val is not None:
                setattr(app, key, val)
        return app
