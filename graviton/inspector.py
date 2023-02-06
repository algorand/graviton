from base64 import b64decode
import csv
from dataclasses import dataclass
from enum import Enum, auto
import io

from tabulate import tabulate
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from algosdk import abi
from graviton.dryrun import (
    assert_error,
    assert_no_error,
)
from graviton.models import ArgType, ExecutionMode, PyTypes


class DryRunProperty(Enum):
    cost = auto()
    budgetAdded = auto()
    budgetConsumed = auto()
    lastLog = auto()
    finalScratch = auto()
    stackTop = auto()
    maxStackHeight = auto()
    status = auto()
    rejected = auto()
    passed = auto()
    error = auto()
    errorMessage = auto()
    globalStateHas = auto()
    localStateHas = auto()
    lastMessage = auto()


DRProp = DryRunProperty
EncodingType = Union[abi.ABIType, str, None]


def mode_has_property(mode: ExecutionMode, assertion_type: "DryRunProperty") -> bool:
    missing: Dict[ExecutionMode, set] = {
        ExecutionMode.Signature: {
            DryRunProperty.cost,
            DryRunProperty.budgetAdded,
            DryRunProperty.budgetConsumed,
            DryRunProperty.lastLog,
        },
        ExecutionMode.Application: set(),
    }
    if assertion_type in missing[mode]:
        return False

    return True


@dataclass
class TealVal:
    i: int = 0
    b: str = ""
    is_b: Optional[bool] = None
    hide_empty: bool = True

    @classmethod
    def from_stack(cls, d: dict) -> "TealVal":
        return TealVal(d["uint"], d["bytes"], d["type"] == 1, hide_empty=False)

    @classmethod
    def from_scratch(cls, d: dict) -> "TealVal":
        return TealVal(d["uint"], d["bytes"], len(d["bytes"]) > 0)

    def is_empty(self) -> bool:
        return not (self.i or self.b)

    def __str__(self) -> str:
        if self.hide_empty and self.is_empty():
            return ""

        assert self.is_b is not None, "can't handle StackVariable with empty type"
        return f"0x{b64decode(self.b).hex()}" if self.is_b else str(self.i)

    def as_python_type(self) -> Union[int, str, None]:
        if self.is_b is None:
            return None
        return str(self) if self.is_b else self.i


@dataclass
class DryRunResults:
    steps_executed: int
    program_counters: List[int]
    teal_line_numbers: List[int]
    teal_source_lines: List[str]
    stack_evolution: List[str]
    scratch_evolution: List[List[str]]
    final_scratch_state: Dict[int, TealVal]
    slots_used: List[int]
    raw_stacks: List[list]

    @classmethod
    def scrape(
        cls,
        trace,
        lines,
        scratch_colon: str = "->",
        scratch_verbose: bool = False,
    ) -> "DryRunResults":
        pcs = [t["pc"] for t in trace]
        line_nums = [t["line"] for t in trace]

        def line_or_err(i, ln):
            line = lines[ln - 1]
            err = trace[i].get("error")
            return err if err else line

        tls = [line_or_err(i, ln) for i, ln in enumerate(line_nums)]
        N = len(pcs)
        assert N == len(tls), f"mismatch of lengths in pcs v. tls ({N} v. {len(tls)})"

        # process stack var's
        raw_stacks = [
            [TealVal.from_stack(s) for s in x] for x in [t["stack"] for t in trace]
        ]
        stacks = [f"[{', '.join(map(str,stack))}]" for stack in raw_stacks]
        assert N == len(
            stacks
        ), f"mismatch of lengths in tls v. stacks ({N} v. {len(stacks)})"

        # process scratch var's
        _scr1 = [
            [TealVal.from_scratch(s) for s in x]
            for x in [t.get("scratch", []) for t in trace]
        ]
        _scr2 = [
            {i: s for i, s in enumerate(scratch) if not s.is_empty()}
            for scratch in _scr1
        ]
        slots_used = sorted(set().union(*(s.keys() for s in _scr2)))
        final_scratch_state = _scr2[-1]
        if not scratch_verbose:

            def compute_delta(prev, curr):
                pks, cks = set(prev.keys()), set(curr.keys())
                new_keys = cks - pks
                if new_keys:
                    return {k: curr[k] for k in new_keys}
                return {k: v for k, v in curr.items() if prev[k] != v}

            scratch_deltas: List[Dict[int, TealVal]] = [_scr2[0]]
            for i in range(1, len(_scr2)):
                scratch_deltas.append(compute_delta(_scr2[i - 1], _scr2[i]))

            scratches = [
                [f"{i}{scratch_colon}{v}" for i, v in scratch.items()]
                for scratch in scratch_deltas
            ]
        else:
            scratches = [
                [
                    f"{i}{scratch_colon}{scratch[i]}" if i in scratch else ""
                    for i in slots_used
                ]
                for scratch in _scr2
            ]

        assert N == len(
            scratches
        ), f"mismatch of lengths in tls v. scratches ({N} v. {len(scratches)})"

        bbr = cls(
            N,
            pcs,
            line_nums,
            tls,
            stacks,
            scratches,
            final_scratch_state,
            slots_used,
            raw_stacks,
        )
        bbr.assert_well_defined()
        return bbr

    def assert_well_defined(self):
        assert all(
            self.steps_executed == len(x)
            for x in (
                self.program_counters,
                self.teal_source_lines,
                self.stack_evolution,
                self.scratch_evolution,
            )
        ), f"some mismatch in trace sizes: all expected to be {self.steps_executed}"

    def __str__(self) -> str:
        return f"BlackBoxResult(steps_executed={self.steps_executed})"

    def steps(self) -> int:
        return self.steps_executed

    def final_stack(self) -> str:
        return self.stack_evolution[-1]

    def final_stack_top(self) -> Union[int, str, None]:
        final_stack = self.raw_stacks[-1]
        if not final_stack:
            return None
        top = final_stack[-1]
        return str(top) if top.is_b else top.i

    def max_stack_height(self) -> int:
        return max(len(s) for s in self.raw_stacks)

    def final_scratch(
        self, with_formatting: bool = False
    ) -> Dict[Union[int, str], Union[int, str]]:
        unformatted: Dict[Union[int, str], Union[int, str]] = {
            i: str(s) if s.is_b else s.i for i, s in self.final_scratch_state.items()
        }
        if not with_formatting:
            return unformatted
        return {f"s@{i:03}": s for i, s in unformatted.items()}

    def slots(self) -> List[int]:
        return self.slots_used

    def final_as_row(self) -> dict:
        return {
            "steps": self.steps(),
            " top_of_stack": self.final_stack_top() or "",
            "max_stack_height": self.max_stack_height(),
            **self.final_scratch(with_formatting=True),  # type: ignore
        }


class DryRunInspector:
    """Methods to extract information from a single dry run transaction.

    The class contains convenience methods and properties for inspecting
    dry run execution results on a _single transaction_ and for making
    assertions in tests.

    For example, let's execute a dry run for a logic sig teal program that purportedly computes $`x^2`$
    (see [lsig_square.teal](../../x/blackbox/teal/lsig_square.teal) for one such example).
    So assume you have a string `teal` containing that TEAL source and run the following:

    ```python
    >>> algod = get_algod()
    >>> x = 9
    >>> args = (x,)
    >>> inspector = DryRunExecutor.dryrun_logicsig(algod, teal, args)
    >>> assert inspector.status() == "PASS"
    >>> assert inspector.stack_stop() == x ** 2
    ```
    In the above we have asserted the the program has succesfully exited with
    status "PASS" and that the top of the stack contained $`x^2 = 9`$.
    The _assertable properties_ were `status()` and `stack_top()`.

    DryRunInspector provides the following **assertable properties**:
    * `cost`
        - net opcode budget consumed during execution
        - derived property: cost = budget_consumed - budget_added
        - only available for apps
    * `budget_added`
        - total opcode budget increase during execution
        - only available for apps
    * `budget_consumed`
        - total opcode budget consumed during execution
        - only available for apps
    * `last_log`
        - the final hex bytes that was logged during execution (apps only)
        - only available for apps
    * `logs`
        - similar to `last_log` but a list of _all_ the printed logs
    * `final_scratch`
        - the final scratch slot state contents represented as a dictionary
        - CAVEAT: slots containing a type's zero-value (0 or "") are not reported
    * `max_stack_height`
        - the maximum height of stack had during execution
    * `stack_top`
        - the contents of the top of the stack and the end of execution
    * `status`
        - either "PASS" when the execution succeeded or "REJECT" otherwise
    * `passed`
        - shorthand for `status() == "PASS"`
    * `rejected`
        - shorthand for `status() == "REJECT"`
    * `error` with optional `contains` matching
        - when no contains is provided, returns True exactly when execution fails due to error
        - when contains given, only return True if an error occured included contains

    A.B.I. types and last_log():

    When an `abi_type` is provided, `last_log()` will be decoded using that type after removal of
    a presumed 4-byte return prefix. To suppress removing the 4-byte prefix set `config(has_abi_prefix=False)`.
    To suppress decoding the last log entry altogether, and show the raw hex, set `config(suppress_abi=True)`.
    """

    CONFIG_OPTIONS = {"suppress_abi", "has_abi_prefix", "show_internal_errors_on_log"}

    def __init__(
        self,
        dryrun_resp: dict,
        txn_index: int,
        args: Sequence[PyTypes],
        encoded_args: List[ArgType],
        abi_type: EncodingType = None,
    ):
        txns = dryrun_resp.get("txns", [])
        assert txns, "Dry Run response is missing transactions"

        assert (
            0 <= txn_index < len(txns)
        ), f"Out of bounds txn_index {txn_index} when there are only {len(txns)} transactions in the Dry Run response"

        txn = txns[txn_index]
        self.args = args
        self.encoded_args = encoded_args

        self.mode: ExecutionMode = self.get_txn_mode(txn)
        self.parent_dryrun_response: dict = dryrun_resp
        self.txn: dict = txn
        self.extracts: dict = self.extract_all(self.txn, self.is_app())
        self.black_box_results: DryRunResults = self.extracts["bbr"]
        self.abi_type = abi_type

        # config options:
        self.suppress_abi: bool
        self.has_abi_prefix: bool
        self.show_internal_errors_on_log: bool
        self.config(
            suppress_abi=False,
            has_abi_prefix=bool(self.abi_type),
            show_internal_errors_on_log=True,
        )

    def method_selector_param(self) -> Optional[str]:
        return cast(str, self.args[0]) if self.abi_type else None

    def abi_params_or_args(self) -> Tuple[PyTypes, ...]:
        return tuple(self.args[1:] if self.abi_type else self.args)

    def config(self, **kwargs: bool):
        bad_keys = set(kwargs.keys()) - self.CONFIG_OPTIONS
        if bad_keys:
            raise ValueError(f"unknown config options: {bad_keys}")

        for k, v in kwargs.items():
            assert isinstance(
                v, bool
            ), f"configuration {k}=[{v}] must be bool but was {type(v)}"

            setattr(self, k, v)

    def is_app(self) -> bool:
        return self.mode == ExecutionMode.Application

    @classmethod
    def get_txn_mode(cls, txn: dict) -> ExecutionMode:
        """
        Guess the mode based on location of traces. If no luck, raise an AssertionError
        """
        keyset = set(txn.keys())
        akey, lskey = "app-call-trace", "logic-sig-trace"
        assert (
            len({akey, lskey} & keyset) == 1
        ), f"ambiguous mode for dry run transaction: expected exactly one of '{akey}', '{lskey}' to be in keyset {keyset}"

        if akey in keyset:
            return ExecutionMode.Application

        return ExecutionMode.Signature

    @classmethod
    def from_single_response(
        cls,
        dryrun_resp: dict,
        args: Sequence[PyTypes],
        encoded_args: List[ArgType],
        abi_type: EncodingType = None,
    ) -> "DryRunInspector":
        error = dryrun_resp.get("error")
        assert not error, f"dryrun response included the following error: [{error}]"

        txns = dryrun_resp.get("txns") or []
        assert (
            len(txns) == 1
        ), f"require exactly 1 dry run transaction to create a singleton but had {len(txns)} instead"

        return cls(dryrun_resp, 0, args, encoded_args, abi_type=abi_type)

    def dig(self, dr_property: DryRunProperty, **kwargs: Dict[str, Any]) -> Any:
        """Main router for assertable properties"""
        txn = self.txn
        bbr = self.black_box_results

        assert mode_has_property(
            self.mode, dr_property
        ), f"{self.mode} cannot handle dig information from txn for assertion type {dr_property}"

        if dr_property == DryRunProperty.cost:
            # cost is treated as a derived property if budget-consumed and budget-added is available
            return txn["budget-consumed"] - txn["budget-added"]

        if dr_property == DryRunProperty.budgetAdded:
            return txn["budget-added"]

        if dr_property == DryRunProperty.budgetConsumed:
            return txn["budget-consumed"]

        if dr_property == DryRunProperty.lastLog:
            last_log = txn.get("logs", [None])[-1]
            if last_log is None:
                return last_log

            last_log = b64decode(last_log).hex()
            if not self.abi_type or self.suppress_abi:
                return last_log

            try:
                if self.has_abi_prefix:
                    # skip the first 8 hex char's == first 4 bytes:
                    last_log = last_log[8:]
                return cast(abi.ABIType, self.abi_type).decode(bytes.fromhex(last_log))
            except Exception as e:
                if self.show_internal_errors_on_log:
                    return str(e)
                raise e

        if dr_property == DryRunProperty.finalScratch:
            return {k: v.as_python_type() for k, v in bbr.final_scratch_state.items()}

        if dr_property == DryRunProperty.stackTop:
            trace = self.extracts["trace"]
            stack = trace[-1]["stack"]
            if not stack:
                return None
            tv = TealVal.from_scratch(stack[-1])
            return tv.as_python_type()

        if dr_property == DryRunProperty.maxStackHeight:
            return max(len(t["stack"]) for t in self.extracts["trace"])

        if dr_property == DryRunProperty.status:
            return self.extracts["status"]

        if dr_property == DryRunProperty.passed:
            return self.extracts["status"] == "PASS"

        if dr_property == DryRunProperty.rejected:
            return self.extracts["status"] == "REJECT"

        if dr_property == DryRunProperty.error:
            """
            * when `contains` kwarg is NOT provided
                - asserts that there was an error
            * when `contains` kwarg IS provided
                - asserts that there was an error AND that it's message includes `contains`'s value
            """
            contains = kwargs.get("contains")
            ok, msg = assert_error(
                self.parent_dryrun_response, contains=contains, enforce=False
            )
            return ok

        if dr_property == DryRunProperty.errorMessage:
            """
            * when there was no error, we return None, else return its msg
            """
            _, msg = assert_no_error(self.parent_dryrun_response, enforce=False)
            return msg if msg else None

        if dr_property == DryRunProperty.lastMessage:
            return self.last_message()

        raise Exception(f"Unknown assert_type {dr_property}")

    def cost(self) -> Optional[int]:
        """Assertable property for the net opcode budget consumed during dry run execution
        return type: int
        available Mode: Application only
        """
        return self.dig(DRProp.cost) if self.is_app() else None

    def budget_added(self) -> Optional[int]:
        """Assertable property for the total opcode budget added with itxns during dry run execution
        return type: int
        available Mode: Application only
        """
        return self.dig(DRProp.budgetAdded) if self.is_app() else None

    def budget_consumed(self) -> Optional[int]:
        """Assertable property for the total opcode budget consumed during dry run execution
        return type: int
        available Mode: Application only
        """
        return self.dig(DRProp.budgetConsumed) if self.is_app() else None

    def last_log(self) -> Any:
        """Assertable property for the last log that was printed during dry run execution
        return type: string representing the hex bytes of the final log
        available Mode: Application only
        """
        if not self.is_app():
            return None

        return self.dig(DRProp.lastLog)

    def stack_top(self) -> Union[int, str]:
        """Assertable property for the contents of the top of the stack and the end of a dry run execution
        return type: int or string
        available: all modes
        """
        return self.dig(DRProp.stackTop)

    def logs(self) -> Optional[List[str]]:
        """Assertable property for all the logs that were printed during dry run execution
        return type: list of strings representing hex bytes of the logs
        available Mode: Application only
        """
        return self.extracts["logs"]

    def final_scratch(self) -> Dict[int, Union[int, str]]:
        """Assertable property for the scratch slots and their contents at the end of dry run execution
        return type: dictionary from strings to int's or strings
        available: all modes
        CAVEAT: slots containing a type's zero-value (0 or "") are not reported
        """
        return self.dig(DRProp.finalScratch)

    def max_stack_height(self) -> int:
        """Assertable property for the maximum height the stack had during a dry run execution
        return type: int
        available: all modes
        """
        return self.dig(DRProp.maxStackHeight)

    def status(self) -> str:
        """Assertable property for the program run status at the end of dry run execution
        return type: string (either "PASS" or "REJECT")
        available: all modes
        """
        return self.dig(DRProp.status)

    def passed(self) -> bool:
        """Assertable property for the program's dry run execution having SUCCEEDED
        return type: bool
        available: all modes
        """
        return self.dig(DRProp.passed)

    def rejected(self) -> bool:
        """Assertable property for the program's dry run execution having FAILED
        return type: bool
        available: all modes
        """
        return self.dig(DRProp.rejected)

    def error(self, contains=None) -> bool:
        """Assertable property for a program having failed during dry run execution due to an error.
        The optional `contains` parameter allows specifying a particular string
        expected to be a _substring_ of the error's message. In case the program errors, but
        the contains did not match the actual error, False is returned.
            return type: bool
            available: all modes
        """
        return self.dig(DRProp.error, contains=contains)

    def error_message(self) -> Union[bool, str]:
        """Assertable property for the error message that a program produces.
        return type: None (in the case of no error) or string with the error message, in case of error
        available: all modes
        """
        return self.dig(DRProp.errorMessage)

    def messages(self) -> List[str]:
        return self.extracts["messages"]

    def last_message(self) -> Optional[str]:
        return self.messages()[-1] if self.messages() else None

    def local_deltas(self) -> dict:
        return self.extracts["ldeltas"]

    def global_delta(self) -> dict:
        return self.extracts["gdelta"]

    def tabulate(
        self,
        col_max: int,
        *,
        scratch_verbose: bool = False,
        scratch_before_stack: bool = True,
        last_steps: int = 100,
    ):
        """Produce a string that when printed shows the evolution of a dry run.

        This is similar to DryrunTestCaseMixin's `pprint()` but also includes scratch
        variable evolution.

        For example, calling `tabulate()` with default values produces something like:

           step |   PC# |   L# | Teal                   | Scratch   | Stack
        --------+-------+------+------------------------+-----------+----------------------
              1 |     1 |    1 | #pragma version 6      |           | []
              2 |     4 |    2 | txna ApplicationArgs 0 |           | [0x0000000000000002]
              3 |     5 |    3 | btoi                   |           | [2]
              4 |    17 |   11 | label1:                |           | [2]
              5 |    19 |   12 | store 0                | 0->2      | []
              6 |    21 |   13 | load 0                 |           | [2]
              7 |    23 |   14 | pushint 2              |           | [2, 2]
              8 |    24 |   15 | exp                    |           | [4]
              9 |     8 |    4 | callsub label1         |           | [4]
             10 |    10 |    5 | store 1                | 1->4      | []
             11 |    12 |    6 | load 1                 |           | [4]
             12 |    13 |    7 | itob                   |           | [0x0000000000000004]
             13 |    14 |    8 | log                    |           | []
             14 |    16 |    9 | load 1                 |           | [4]
             15 |    25 |   16 | retsub                 |           | [4]
        """
        assert not (
            scratch_verbose and scratch_before_stack
        ), "Cannot request scratch columns before stack when verbose"
        bbr = self.black_box_results

        def empty_hack(se):
            return se if se else [""]

        rows = [
            list(
                map(
                    str,
                    [
                        i + 1,
                        bbr.program_counters[i],
                        bbr.teal_line_numbers[i],
                        bbr.teal_source_lines[i],
                        bbr.stack_evolution[i],
                        *empty_hack(bbr.scratch_evolution[i]),
                    ],
                )
            )
            for i in range(bbr.steps_executed)
        ]
        if col_max and col_max > 0:
            rows = [[x[:col_max] for x in row] for row in rows]
        headers = [
            "step",
            "PC#",
            "L#",
            "Teal",
            "Stack",
            *([f"S@{s}" for s in bbr.slots_used] if scratch_verbose else ["Scratch"]),
        ]
        if scratch_before_stack:
            # with assertion above, we know that there is only one
            # scratch column and it's at the very end
            headers[-1], headers[-2] = headers[-2], headers[-1]
            for i in range(len(rows)):
                rows[i][-1], rows[i][-2] = rows[i][-2], rows[i][-1]

        if last_steps >= 0:
            rows = rows[-last_steps:]
        table = tabulate(rows, headers=headers, tablefmt="presto")
        return table

    def report(
        self,
        args: Optional[Sequence[PyTypes]] = None,
        msg: str = "Dry Run Inspector Report",
        row: int = 0,
        last_steps: int = 100,
    ) -> str:
        bbr = self.black_box_results
        if args is None:
            args = self.args
        return f"""===============
    <<<<<<<<<<<{msg}>>>>>>>>>>>
    ===============
    App Trace:
    {self.tabulate(-1, last_steps=last_steps)}
    ===============
    MODE: {self.mode}
    TOTAL COST: {self.cost()}
    ===============
    FINAL MESSAGE: {self.last_message()}
    ===============
    Messages: {self.messages()}
    Logs: {self.logs()}
    ===============
    -----{bbr}-----
    TOTAL STEPS: {bbr.steps()}
    FINAL STACK: {bbr.final_stack()}
    FINAL STACK TOP: {bbr.final_stack_top()}
    MAX STACK HEIGHT: {bbr.max_stack_height()}
    FINAL SCRATCH: {bbr.final_scratch()}
    SLOTS USED: {bbr.slots()}
    FINAL AS ROW: {bbr.final_as_row()}
    ===============
    Global Delta:
    {self.global_delta()}
    ===============
    Local Delta:
    {self.local_deltas()}
    ===============
    TXN AS ROW: {self.csv_row(row)}
    ===============
    <<<<<<<<<<<{msg}>>>>>>>>>>>
    ===============
    """

    def csv_row(self, row_num: int) -> Dict[str, Optional[PyTypes]]:
        return {
            " Run": row_num,
            " budget_added": self.budget_added(),
            " budget_consumed": self.budget_consumed(),
            " cost": self.cost(),
            # back-tick needed to keep Excel/Google sheets from stumbling over hex
            " last_log": f"`{self.last_log()}",
            " final_message": self.last_message(),
            " Status": self.status(),
            **self.black_box_results.final_as_row(),
            **{f"Arg_{i:02}": arg for i, arg in enumerate(self.args)},
        }

    @classmethod
    def csv_report(
        cls,
        inputs: List[Sequence[PyTypes]],
        dr_resps: Sequence["DryRunInspector"],
        txns: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Produce a Comma Separated Values report string capturing important statistics
        for a sequence of dry runs.

        For example, assuming you have a string `teal` which is a TEAL program computing $`x^2`$
        such as this [example program](x/blackbox/teal/app_square.teal).
        Let's run some Exploratory Dry Run Analysis (EDRA) for $`x`$ in the range $`[0, 10]`$:

        ```python
        >>> algod = get_algod()
        >>> inputs = [(x,) for x in range(11)]  # [(0), (1), ... , (10)]
        >>> run_results = DryRunExecutor.dryrun_app_on_sequence(algod, teal, inputs)
        >>> csv = DryRunInspector.csv_report(inputs, run_results)
        >>> print(csv)
        ```
        Then you would get the following output:
        ```plain
        Run, Status, cost, final_message, last_log, top_of_stack,Arg_00,max_stack_height,s@000,s@001,steps
        1,REJECT,14,REJECT,`None,0,0,2,,,15
        2,PASS,14,PASS,`0000000000000001,1,1,2,1,1,15
        3,PASS,14,PASS,`0000000000000004,4,2,2,2,4,15
        4,PASS,14,PASS,`0000000000000009,9,3,2,3,9,15
        5,PASS,14,PASS,`0000000000000010,16,4,2,4,16,15
        6,PASS,14,PASS,`0000000000000019,25,5,2,5,25,15
        7,PASS,14,PASS,`0000000000000024,36,6,2,6,36,15
        8,PASS,14,PASS,`0000000000000031,49,7,2,7,49,15
        9,PASS,14,PASS,`0000000000000040,64,8,2,8,64,15
        10,PASS,14,PASS,`0000000000000051,81,9,2,9,81,15
        ```
        """
        N = len(inputs)
        assert N == len(
            dr_resps
        ), f"cannot produce CSV with unmatching size of inputs ({len(inputs)}) v. drresps ({len(dr_resps)})"
        if txns:
            assert N == len(
                txns
            ), f"cannot produce CSV with unmatching size of inputs ({len(inputs)}) v. txns ({len(txns)})"

        _drrs = [resp.csv_row(i + 1) for i, resp in enumerate(dr_resps)]

        def row(i):
            return {**_drrs[i], **(txns[i] if txns else {})}

        def row_columns(i):
            return row(i).keys()

        with io.StringIO() as csv_str:
            fields = sorted(set().union(*(row_columns(i) for i in range(N))))
            writer = csv.DictWriter(csv_str, fieldnames=fields)
            writer.writeheader()
            for i in range(N):
                writer.writerow(row(i))

            return csv_str.getvalue()

    @classmethod
    def extract_logs(cls, txn):
        return [b64decode(log).hex() for log in txn.get("logs", [])]

    @classmethod
    def extract_cost(cls, txn):
        # cost is treated as a derived property if budget-consumed and budget-added is available
        if "budget-consumed" not in txn or "budget-added" not in txn:
            return None

        return txn["budget-consumed"] - txn["budget-added"]

    @classmethod
    def extract_status(cls, txn, is_app: bool):
        key, idx = ("app-call-messages", 1) if is_app else ("logic-sig-messages", 0)
        return txn[key][idx]

    @classmethod
    def extract_messages(cls, txn, is_app):
        return txn["app-call-messages" if is_app else "logic-sig-messages"]

    @classmethod
    def extract_local_deltas(cls, txn):
        return txn.get("local-deltas", [])

    @classmethod
    def extract_global_delta(cls, txn):
        return txn.get("global-delta", [])

    @classmethod
    def extract_lines(cls, txn, is_app):
        return txn["disassembly" if is_app else "logic-sig-disassembly"]

    @classmethod
    def extract_trace(cls, txn, is_app):
        return txn["app-call-trace" if is_app else "logic-sig-trace"]

    @classmethod
    def extract_all(cls, txn: dict, is_app: bool) -> dict:
        result = {
            "logs": cls.extract_logs(txn),
            "cost": cls.extract_cost(txn),
            "status": cls.extract_status(txn, is_app),
            "messages": cls.extract_messages(txn, is_app),
            "ldeltas": cls.extract_local_deltas(txn),
            "gdelta": cls.extract_global_delta(txn),
            "lines": cls.extract_lines(txn, is_app),
            "trace": cls.extract_trace(txn, is_app),
        }

        result["bbr"] = DryRunResults.scrape(result["trace"], result["lines"])

        return result
