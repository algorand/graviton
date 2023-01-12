from graviton.abi_strategy import PyTypes, ABIStrategy, RandomABIStrategy
from graviton.dryrun import DryRunHelper
from graviton.inspector import DryRunInspector
from graviton.models import ZERO_ADDRESS, ArgType, DryRunAccountType, ExecutionMode


from typing import (
    Any,
    Dict,
    Final,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    cast,
)

from algosdk import abi
from algosdk import atomic_transaction_composer as atc
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.models import DryrunRequest
from algosdk.transaction import (
    OnComplete,
    StateSchema,
    SuggestedParams,
)


TealAndMethodType = Union[Tuple[str], Tuple[str, str]]
EncodingType = Union[abi.ABIType, str, None]


MAX_APP_ARG_LIMIT = atc.AtomicTransactionComposer.MAX_APP_ARG_LIMIT


# class DryRunProperty(Enum):
#     cost = auto()
#     budgetAdded = auto()
#     budgetConsumed = auto()
#     lastLog = auto()
#     finalScratch = auto()
#     stackTop = auto()
#     maxStackHeight = auto()
#     status = auto()
#     rejected = auto()
#     passed = auto()
#     error = auto()
#     errorMessage = auto()
#     globalStateHas = auto()
#     localStateHas = auto()
#     lastMessage = auto()


# DRProp = DryRunProperty


# def mode_has_property(mode: ExecutionMode, assertion_type: "DryRunProperty") -> bool:
#     missing: Dict[ExecutionMode, set] = {
#         ExecutionMode.Signature: {
#             DryRunProperty.cost,
#             DryRunProperty.budgetAdded,
#             DryRunProperty.budgetConsumed,
#             DryRunProperty.lastLog,
#         },
#         ExecutionMode.Application: set(),
#     }
#     if assertion_type in missing[mode]:
#         return False

#     return True


# @dataclass
# class TealVal:
#     i: int = 0
#     b: str = ""
#     is_b: Optional[bool] = None
#     hide_empty: bool = True

#     @classmethod
#     def from_stack(cls, d: dict) -> "TealVal":
#         return TealVal(d["uint"], d["bytes"], d["type"] == 1, hide_empty=False)

#     @classmethod
#     def from_scratch(cls, d: dict) -> "TealVal":
#         return TealVal(d["uint"], d["bytes"], len(d["bytes"]) > 0)

#     def is_empty(self) -> bool:
#         return not (self.i or self.b)

#     def __str__(self) -> str:
#         if self.hide_empty and self.is_empty():
#             return ""

#         assert self.is_b is not None, "can't handle StackVariable with empty type"
#         return f"0x{b64decode(self.b).hex()}" if self.is_b else str(self.i)

#     def as_python_type(self) -> Union[int, str, None]:
#         if self.is_b is None:
#             return None
#         return str(self) if self.is_b else self.i


# @dataclass
# class DryRunResults:
#     steps_executed: int
#     program_counters: List[int]
#     teal_line_numbers: List[int]
#     teal_source_lines: List[str]
#     stack_evolution: List[str]
#     scratch_evolution: List[List[str]]
#     final_scratch_state: Dict[int, TealVal]
#     slots_used: List[int]
#     raw_stacks: List[list]

#     @classmethod
#     def scrape(
#         cls,
#         trace,
#         lines,
#         scratch_colon: str = "->",
#         scratch_verbose: bool = False,
#     ) -> "DryRunResults":
#         pcs = [t["pc"] for t in trace]
#         line_nums = [t["line"] for t in trace]

#         def line_or_err(i, ln):
#             line = lines[ln - 1]
#             err = trace[i].get("error")
#             return err if err else line

#         tls = [line_or_err(i, ln) for i, ln in enumerate(line_nums)]
#         N = len(pcs)
#         assert N == len(tls), f"mismatch of lengths in pcs v. tls ({N} v. {len(tls)})"

#         # process stack var's
#         raw_stacks = [
#             [TealVal.from_stack(s) for s in x] for x in [t["stack"] for t in trace]
#         ]
#         stacks = [f"[{', '.join(map(str,stack))}]" for stack in raw_stacks]
#         assert N == len(
#             stacks
#         ), f"mismatch of lengths in tls v. stacks ({N} v. {len(stacks)})"

#         # process scratch var's
#         _scr1 = [
#             [TealVal.from_scratch(s) for s in x]
#             for x in [t.get("scratch", []) for t in trace]
#         ]
#         _scr2 = [
#             {i: s for i, s in enumerate(scratch) if not s.is_empty()}
#             for scratch in _scr1
#         ]
#         slots_used = sorted(set().union(*(s.keys() for s in _scr2)))
#         final_scratch_state = _scr2[-1]
#         if not scratch_verbose:

#             def compute_delta(prev, curr):
#                 pks, cks = set(prev.keys()), set(curr.keys())
#                 new_keys = cks - pks
#                 if new_keys:
#                     return {k: curr[k] for k in new_keys}
#                 return {k: v for k, v in curr.items() if prev[k] != v}

#             scratch_deltas: List[Dict[int, TealVal]] = [_scr2[0]]
#             for i in range(1, len(_scr2)):
#                 scratch_deltas.append(compute_delta(_scr2[i - 1], _scr2[i]))

#             scratches = [
#                 [f"{i}{scratch_colon}{v}" for i, v in scratch.items()]
#                 for scratch in scratch_deltas
#             ]
#         else:
#             scratches = [
#                 [
#                     f"{i}{scratch_colon}{scratch[i]}" if i in scratch else ""
#                     for i in slots_used
#                 ]
#                 for scratch in _scr2
#             ]

#         assert N == len(
#             scratches
#         ), f"mismatch of lengths in tls v. scratches ({N} v. {len(scratches)})"

#         bbr = cls(
#             N,
#             pcs,
#             line_nums,
#             tls,
#             stacks,
#             scratches,
#             final_scratch_state,
#             slots_used,
#             raw_stacks,
#         )
#         bbr.assert_well_defined()
#         return bbr

#     def assert_well_defined(self):
#         assert all(
#             self.steps_executed == len(x)
#             for x in (
#                 self.program_counters,
#                 self.teal_source_lines,
#                 self.stack_evolution,
#                 self.scratch_evolution,
#             )
#         ), f"some mismatch in trace sizes: all expected to be {self.steps_executed}"

#     def __str__(self) -> str:
#         return f"BlackBoxResult(steps_executed={self.steps_executed})"

#     def steps(self) -> int:
#         return self.steps_executed

#     def final_stack(self) -> str:
#         return self.stack_evolution[-1]

#     def final_stack_top(self) -> Union[int, str, None]:
#         final_stack = self.raw_stacks[-1]
#         if not final_stack:
#             return None
#         top = final_stack[-1]
#         return str(top) if top.is_b else top.i

#     def max_stack_height(self) -> int:
#         return max(len(s) for s in self.raw_stacks)

#     def final_scratch(
#         self, with_formatting: bool = False
#     ) -> Dict[Union[int, str], Union[int, str]]:
#         unformatted: Dict[Union[int, str], Union[int, str]] = {
#             i: str(s) if s.is_b else s.i for i, s in self.final_scratch_state.items()
#         }
#         if not with_formatting:
#             return unformatted
#         return {f"s@{i:03}": s for i, s in unformatted.items()}

#     def slots(self) -> List[int]:
#         return self.slots_used

#     def final_as_row(self) -> dict:
#         return {
#             "steps": self.steps(),
#             " top_of_stack": self.final_stack_top() or "",
#             "max_stack_height": self.max_stack_height(),
#             **self.final_scratch(with_formatting=True),  # type: ignore
#         }


# class DryRunInspector:
#     """Methods to extract information from a single dry run transaction.

#     The class contains convenience methods and properties for inspecting
#     dry run execution results on a _single transaction_ and for making
#     assertions in tests.

#     For example, let's execute a dry run for a logic sig teal program that purportedly computes $`x^2`$
#     (see [lsig_square.teal](../../x/blackbox/teal/lsig_square.teal) for one such example).
#     So assume you have a string `teal` containing that TEAL source and run the following:

#     ```python
#     >>> algod = get_algod()
#     >>> x = 9
#     >>> args = (x,)
#     >>> inspector = DryRunExecutor.dryrun_logicsig(algod, teal, args)
#     >>> assert inspector.status() == "PASS"
#     >>> assert inspector.stack_stop() == x ** 2
#     ```
#     In the above we have asserted the the program has succesfully exited with
#     status "PASS" and that the top of the stack contained $`x^2 = 9`$.
#     The _assertable properties_ were `status()` and `stack_top()`.

#     DryRunInspector provides the following **assertable properties**:
#     * `cost`
#         - net opcode budget consumed during execution
#         - derived property: cost = budget_consumed - budget_added
#         - only available for apps
#     * `budget_added`
#         - total opcode budget increase during execution
#         - only available for apps
#     * `budget_consumed`
#         - total opcode budget consumed during execution
#         - only available for apps
#     * `last_log`
#         - the final hex bytes that was logged during execution (apps only)
#         - only available for apps
#     * `logs`
#         - similar to `last_log` but a list of _all_ the printed logs
#     * `final_scratch`
#         - the final scratch slot state contents represented as a dictionary
#         - CAVEAT: slots containing a type's zero-value (0 or "") are not reported
#     * `max_stack_height`
#         - the maximum height of stack had during execution
#     * `stack_top`
#         - the contents of the top of the stack and the end of execution
#     * `status`
#         - either "PASS" when the execution succeeded or "REJECT" otherwise
#     * `passed`
#         - shorthand for `status() == "PASS"`
#     * `rejected`
#         - shorthand for `status() == "REJECT"`
#     * `error` with optional `contains` matching
#         - when no contains is provided, returns True exactly when execution fails due to error
#         - when contains given, only return True if an error occured included contains

#     A.B.I. types and last_log():

#     When an `abi_type` is provided, `last_log()` will be decoded using that type after removal of
#     a presumed 4-byte return prefix. To suppress removing the 4-byte prefix set `config(has_abi_prefix=False)`.
#     To suppress decoding the last log entry altogether, and show the raw hex, set `config(suppress_abi=True)`.
#     """

#     CONFIG_OPTIONS = {"suppress_abi", "has_abi_prefix", "show_internal_errors_on_log"}

#     def __init__(
#         self,
#         dryrun_resp: dict,
#         txn_index: int,
#         args: Sequence[PyTypes],
#         encoded_args: List[ArgType],
#         abi_type: Optional[abi.ABIType] = None,
#     ):
#         txns = dryrun_resp.get("txns", [])
#         assert txns, "Dry Run response is missing transactions"

#         assert (
#             0 <= txn_index < len(txns)
#         ), f"Out of bounds txn_index {txn_index} when there are only {len(txns)} transactions in the Dry Run response"

#         txn = txns[txn_index]
#         self.args = args
#         self.encoded_args = encoded_args

#         self.mode: ExecutionMode = self.get_txn_mode(txn)
#         self.parent_dryrun_response: dict = dryrun_resp
#         self.txn: dict = txn
#         self.extracts: dict = self.extract_all(self.txn, self.is_app())
#         self.black_box_results: DryRunResults = self.extracts["bbr"]
#         self.abi_type = abi_type

#         # config options:
#         self.suppress_abi: bool
#         self.has_abi_prefix: bool
#         self.show_internal_errors_on_log: bool
#         self.config(
#             suppress_abi=False,
#             has_abi_prefix=bool(self.abi_type),
#             show_internal_errors_on_log=True,
#         )

#     def method_selector_param(self) -> Optional[str]:
#         return cast(str, self.args[0]) if self.abi_type else None

#     def abi_params_or_args(self) -> Tuple[PyTypes, ...]:
#         return tuple(self.args[1:] if self.abi_type else self.args)

#     def config(self, **kwargs: bool):
#         bad_keys = set(kwargs.keys()) - self.CONFIG_OPTIONS
#         if bad_keys:
#             raise ValueError(f"unknown config options: {bad_keys}")

#         for k, v in kwargs.items():
#             assert isinstance(
#                 v, bool
#             ), f"configuration {k}=[{v}] must be bool but was {type(v)}"

#             setattr(self, k, v)

#     def is_app(self) -> bool:
#         return self.mode == ExecutionMode.Application

#     @classmethod
#     def get_txn_mode(cls, txn: dict) -> ExecutionMode:
#         """
#         Guess the mode based on location of traces. If no luck, raise an AssertionError
#         """
#         keyset = set(txn.keys())
#         akey, lskey = "app-call-trace", "logic-sig-trace"
#         assert (
#             len({akey, lskey} & keyset) == 1
#         ), f"ambiguous mode for dry run transaction: expected exactly one of '{akey}', '{lskey}' to be in keyset {keyset}"

#         if akey in keyset:
#             return ExecutionMode.Application

#         return ExecutionMode.Signature

#     @classmethod
#     def from_single_response(
#         cls,
#         dryrun_resp: dict,
#         args: Sequence[PyTypes],
#         encoded_args: List[ArgType],
#         abi_type: Optional[abi.ABIType] = None,
#     ) -> "DryRunInspector":
#         error = dryrun_resp.get("error")
#         assert not error, f"dryrun response included the following error: [{error}]"

#         txns = dryrun_resp.get("txns") or []
#         assert (
#             len(txns) == 1
#         ), f"require exactly 1 dry run transaction to create a singleton but had {len(txns)} instead"

#         return cls(dryrun_resp, 0, args, encoded_args, abi_type=abi_type)

#     def dig(self, dr_property: DryRunProperty, **kwargs: Dict[str, Any]) -> Any:
#         """Main router for assertable properties"""
#         txn = self.txn
#         bbr = self.black_box_results

#         assert mode_has_property(
#             self.mode, dr_property
#         ), f"{self.mode} cannot handle dig information from txn for assertion type {dr_property}"

#         if dr_property == DryRunProperty.cost:
#             # cost is treated as a derived property if budget-consumed and budget-added is available
#             return txn["budget-consumed"] - txn["budget-added"]

#         if dr_property == DryRunProperty.budgetAdded:
#             return txn["budget-added"]

#         if dr_property == DryRunProperty.budgetConsumed:
#             return txn["budget-consumed"]

#         if dr_property == DryRunProperty.lastLog:
#             last_log = txn.get("logs", [None])[-1]
#             if last_log is None:
#                 return last_log

#             last_log = b64decode(last_log).hex()
#             if not self.abi_type or self.suppress_abi:
#                 return last_log

#             try:
#                 if self.has_abi_prefix:
#                     # skip the first 8 hex char's == first 4 bytes:
#                     last_log = last_log[8:]
#                 return self.abi_type.decode(bytes.fromhex(last_log))
#             except Exception as e:
#                 if self.show_internal_errors_on_log:
#                     return str(e)
#                 raise e

#         if dr_property == DryRunProperty.finalScratch:
#             return {k: v.as_python_type() for k, v in bbr.final_scratch_state.items()}

#         if dr_property == DryRunProperty.stackTop:
#             trace = self.extracts["trace"]
#             stack = trace[-1]["stack"]
#             if not stack:
#                 return None
#             tv = TealVal.from_scratch(stack[-1])
#             return tv.as_python_type()

#         if dr_property == DryRunProperty.maxStackHeight:
#             return max(len(t["stack"]) for t in self.extracts["trace"])

#         if dr_property == DryRunProperty.status:
#             return self.extracts["status"]

#         if dr_property == DryRunProperty.passed:
#             return self.extracts["status"] == "PASS"

#         if dr_property == DryRunProperty.rejected:
#             return self.extracts["status"] == "REJECT"

#         if dr_property == DryRunProperty.error:
#             """
#             * when `contains` kwarg is NOT provided
#                 - asserts that there was an error
#             * when `contains` kwarg IS provided
#                 - asserts that there was an error AND that it's message includes `contains`'s value
#             """
#             contains = kwargs.get("contains")
#             ok, msg = assert_error(
#                 self.parent_dryrun_response, contains=contains, enforce=False
#             )
#             return ok

#         if dr_property == DryRunProperty.errorMessage:
#             """
#             * when there was no error, we return None, else return its msg
#             """
#             _, msg = assert_no_error(self.parent_dryrun_response, enforce=False)
#             return msg if msg else None

#         if dr_property == DryRunProperty.lastMessage:
#             return self.last_message()

#         raise Exception(f"Unknown assert_type {dr_property}")

#     def cost(self) -> Optional[int]:
#         """Assertable property for the net opcode budget consumed during dry run execution
#         return type: int
#         available Mode: Application only
#         """
#         return self.dig(DRProp.cost) if self.is_app() else None

#     def budget_added(self) -> Optional[int]:
#         """Assertable property for the total opcode budget added with itxns during dry run execution
#         return type: int
#         available Mode: Application only
#         """
#         return self.dig(DRProp.budgetAdded) if self.is_app() else None

#     def budget_consumed(self) -> Optional[int]:
#         """Assertable property for the total opcode budget consumed during dry run execution
#         return type: int
#         available Mode: Application only
#         """
#         return self.dig(DRProp.budgetConsumed) if self.is_app() else None

#     def last_log(self) -> Optional[str]:
#         """Assertable property for the last log that was printed during dry run execution
#         return type: string representing the hex bytes of the final log
#         available Mode: Application only
#         """
#         if not self.is_app():
#             return None

#         return self.dig(DRProp.lastLog)

#     def stack_top(self) -> Union[int, str]:
#         """Assertable property for the contents of the top of the stack and the end of a dry run execution
#         return type: int or string
#         available: all modes
#         """
#         return self.dig(DRProp.stackTop)

#     def logs(self) -> Optional[List[str]]:
#         """Assertable property for all the logs that were printed during dry run execution
#         return type: list of strings representing hex bytes of the logs
#         available Mode: Application only
#         """
#         return self.extracts["logs"]

#     def final_scratch(self) -> Dict[int, Union[int, str]]:
#         """Assertable property for the scratch slots and their contents at the end of dry run execution
#         return type: dictionary from strings to int's or strings
#         available: all modes
#         CAVEAT: slots containing a type's zero-value (0 or "") are not reported
#         """
#         return self.dig(DRProp.finalScratch)

#     def max_stack_height(self) -> int:
#         """Assertable property for the maximum height the stack had during a dry run execution
#         return type: int
#         available: all modes
#         """
#         return self.dig(DRProp.maxStackHeight)

#     def status(self) -> str:
#         """Assertable property for the program run status at the end of dry run execution
#         return type: string (either "PASS" or "REJECT")
#         available: all modes
#         """
#         return self.dig(DRProp.status)

#     def passed(self) -> bool:
#         """Assertable property for the program's dry run execution having SUCCEEDED
#         return type: bool
#         available: all modes
#         """
#         return self.dig(DRProp.passed)

#     def rejected(self) -> bool:
#         """Assertable property for the program's dry run execution having FAILED
#         return type: bool
#         available: all modes
#         """
#         return self.dig(DRProp.rejected)

#     def error(self, contains=None) -> bool:
#         """Assertable property for a program having failed during dry run execution due to an error.
#         The optional `contains` parameter allows specifying a particular string
#         expected to be a _substring_ of the error's message. In case the program errors, but
#         the contains did not match the actual error, False is returned.
#             return type: bool
#             available: all modes
#         """
#         return self.dig(DRProp.error, contains=contains)

#     def error_message(self) -> Union[bool, str]:
#         """Assertable property for the error message that a program produces.
#         return type: None (in the case of no error) or string with the error message, in case of error
#         available: all modes
#         """
#         return self.dig(DRProp.errorMessage)

#     def messages(self) -> List[str]:
#         return self.extracts["messages"]

#     def last_message(self) -> Optional[str]:
#         return self.messages()[-1] if self.messages() else None

#     def local_deltas(self) -> dict:
#         return self.extracts["ldeltas"]

#     def global_delta(self) -> dict:
#         return self.extracts["gdelta"]

#     def tabulate(
#         self,
#         col_max: int,
#         *,
#         scratch_verbose: bool = False,
#         scratch_before_stack: bool = True,
#         last_steps: int = 100,
#     ):
#         """Produce a string that when printed shows the evolution of a dry run.

#         This is similar to DryrunTestCaseMixin's `pprint()` but also includes scratch
#         variable evolution.

#         For example, calling `tabulate()` with default values produces something like:

#            step |   PC# |   L# | Teal                   | Scratch   | Stack
#         --------+-------+------+------------------------+-----------+----------------------
#               1 |     1 |    1 | #pragma version 6      |           | []
#               2 |     4 |    2 | txna ApplicationArgs 0 |           | [0x0000000000000002]
#               3 |     5 |    3 | btoi                   |           | [2]
#               4 |    17 |   11 | label1:                |           | [2]
#               5 |    19 |   12 | store 0                | 0->2      | []
#               6 |    21 |   13 | load 0                 |           | [2]
#               7 |    23 |   14 | pushint 2              |           | [2, 2]
#               8 |    24 |   15 | exp                    |           | [4]
#               9 |     8 |    4 | callsub label1         |           | [4]
#              10 |    10 |    5 | store 1                | 1->4      | []
#              11 |    12 |    6 | load 1                 |           | [4]
#              12 |    13 |    7 | itob                   |           | [0x0000000000000004]
#              13 |    14 |    8 | log                    |           | []
#              14 |    16 |    9 | load 1                 |           | [4]
#              15 |    25 |   16 | retsub                 |           | [4]
#         """
#         assert not (
#             scratch_verbose and scratch_before_stack
#         ), "Cannot request scratch columns before stack when verbose"
#         bbr = self.black_box_results

#         def empty_hack(se):
#             return se if se else [""]

#         rows = [
#             list(
#                 map(
#                     str,
#                     [
#                         i + 1,
#                         bbr.program_counters[i],
#                         bbr.teal_line_numbers[i],
#                         bbr.teal_source_lines[i],
#                         bbr.stack_evolution[i],
#                         *empty_hack(bbr.scratch_evolution[i]),
#                     ],
#                 )
#             )
#             for i in range(bbr.steps_executed)
#         ]
#         if col_max and col_max > 0:
#             rows = [[x[:col_max] for x in row] for row in rows]
#         headers = [
#             "step",
#             "PC#",
#             "L#",
#             "Teal",
#             "Stack",
#             *([f"S@{s}" for s in bbr.slots_used] if scratch_verbose else ["Scratch"]),
#         ]
#         if scratch_before_stack:
#             # with assertion above, we know that there is only one
#             # scratch column and it's at the very end
#             headers[-1], headers[-2] = headers[-2], headers[-1]
#             for i in range(len(rows)):
#                 rows[i][-1], rows[i][-2] = rows[i][-2], rows[i][-1]

#         if last_steps >= 0:
#             rows = rows[-last_steps:]
#         table = tabulate(rows, headers=headers, tablefmt="presto")
#         return table

#     def report(
#         self,
#         args: Optional[Sequence[PyTypes]] = None,
#         msg: str = "Dry Run Inspector Report",
#         row: int = 0,
#         last_steps: int = 100,
#     ) -> str:
#         bbr = self.black_box_results
#         if args is None:
#             args = self.args
#         return f"""===============
#     <<<<<<<<<<<{msg}>>>>>>>>>>>
#     ===============
#     App Trace:
#     {self.tabulate(-1, last_steps=last_steps)}
#     ===============
#     MODE: {self.mode}
#     TOTAL COST: {self.cost()}
#     ===============
#     FINAL MESSAGE: {self.last_message()}
#     ===============
#     Messages: {self.messages()}
#     Logs: {self.logs()}
#     ===============
#     -----{bbr}-----
#     TOTAL STEPS: {bbr.steps()}
#     FINAL STACK: {bbr.final_stack()}
#     FINAL STACK TOP: {bbr.final_stack_top()}
#     MAX STACK HEIGHT: {bbr.max_stack_height()}
#     FINAL SCRATCH: {bbr.final_scratch()}
#     SLOTS USED: {bbr.slots()}
#     FINAL AS ROW: {bbr.final_as_row()}
#     ===============
#     Global Delta:
#     {self.global_delta()}
#     ===============
#     Local Delta:
#     {self.local_deltas()}
#     ===============
#     TXN AS ROW: {self.csv_row(row, args)}
#     ===============
#     <<<<<<<<<<<{msg}>>>>>>>>>>>
#     ===============
#     """

#     def csv_row(
#         self, row_num: int, args: Sequence[PyTypes]
#     ) -> Dict[str, Optional[PyTypes]]:
#         return {
#             " Run": row_num,
#             " cost": self.cost(),
#             # back-tick needed to keep Excel/Google sheets from stumbling over hex
#             " last_log": f"`{self.last_log()}",
#             " final_message": self.last_message(),
#             " Status": self.status(),
#             **self.black_box_results.final_as_row(),
#             **{f"Arg_{i:02}": arg for i, arg in enumerate(args)},
#         }

#     @classmethod
#     def csv_report(
#         cls,
#         inputs: List[Sequence[PyTypes]],
#         dr_resps: List["DryRunInspector"],
#         txns: Optional[List[Dict[str, Any]]] = None,
#     ) -> str:
#         """Produce a Comma Separated Values report string capturing important statistics
#         for a sequence of dry runs.

#         For example, assuming you have a string `teal` which is a TEAL program computing $`x^2`$
#         such as this [example program](x/blackbox/teal/app_square.teal).
#         Let's run some Exploratory Dry Run Analysis (EDRA) for $`x`$ in the range $`[0, 10]`$:

#         ```python
#         >>> algod = get_algod()
#         >>> inputs = [(x,) for x in range(11)]  # [(0), (1), ... , (10)]
#         >>> run_results = DryRunExecutor.dryrun_app_on_sequence(algod, teal, inputs)
#         >>> csv = DryRunInspector.csv_report(inputs, run_results)
#         >>> print(csv)
#         ```
#         Then you would get the following output:
#         ```plain
#         Run, Status, cost, final_message, last_log, top_of_stack,Arg_00,max_stack_height,s@000,s@001,steps
#         1,REJECT,14,REJECT,`None,0,0,2,,,15
#         2,PASS,14,PASS,`0000000000000001,1,1,2,1,1,15
#         3,PASS,14,PASS,`0000000000000004,4,2,2,2,4,15
#         4,PASS,14,PASS,`0000000000000009,9,3,2,3,9,15
#         5,PASS,14,PASS,`0000000000000010,16,4,2,4,16,15
#         6,PASS,14,PASS,`0000000000000019,25,5,2,5,25,15
#         7,PASS,14,PASS,`0000000000000024,36,6,2,6,36,15
#         8,PASS,14,PASS,`0000000000000031,49,7,2,7,49,15
#         9,PASS,14,PASS,`0000000000000040,64,8,2,8,64,15
#         10,PASS,14,PASS,`0000000000000051,81,9,2,9,81,15
#         ```
#         """
#         N = len(inputs)
#         assert N == len(
#             dr_resps
#         ), f"cannot produce CSV with unmatching size of inputs ({len(inputs)}) v. drresps ({len(dr_resps)})"
#         if txns:
#             assert N == len(
#                 txns
#             ), f"cannot produce CSV with unmatching size of inputs ({len(inputs)}) v. txns ({len(txns)})"

#         _drrs = [resp.csv_row(i + 1, inputs[i]) for i, resp in enumerate(dr_resps)]

#         def row(i):
#             return {**_drrs[i], **(txns[i] if txns else {})}

#         def row_columns(i):
#             return row(i).keys()

#         with io.StringIO() as csv_str:
#             fields = sorted(set().union(*(row_columns(i) for i in range(N))))
#             writer = csv.DictWriter(csv_str, fieldnames=fields)
#             writer.writeheader()
#             for i in range(N):
#                 writer.writerow(row(i))

#             return csv_str.getvalue()

#     @classmethod
#     def extract_logs(cls, txn):
#         return [b64decode(log).hex() for log in txn.get("logs", [])]

#     @classmethod
#     def extract_cost(cls, txn):
#         # cost is treated as a derived property if budget-consumed and budget-added is available
#         if "budget-consumed" not in txn or "budget-added" not in txn:
#             return None

#         return txn["budget-consumed"] - txn["budget-added"]

#     @classmethod
#     def extract_status(cls, txn, is_app: bool):
#         key, idx = ("app-call-messages", 1) if is_app else ("logic-sig-messages", 0)
#         return txn[key][idx]

#     @classmethod
#     def extract_messages(cls, txn, is_app):
#         return txn["app-call-messages" if is_app else "logic-sig-messages"]

#     @classmethod
#     def extract_local_deltas(cls, txn):
#         return txn.get("local-deltas", [])

#     @classmethod
#     def extract_global_delta(cls, txn):
#         return txn.get("global-delta", [])

#     @classmethod
#     def extract_lines(cls, txn, is_app):
#         return txn["disassembly" if is_app else "logic-sig-disassembly"]

#     @classmethod
#     def extract_trace(cls, txn, is_app):
#         return txn["app-call-trace" if is_app else "logic-sig-trace"]

#     @classmethod
#     def extract_all(cls, txn: dict, is_app: bool) -> dict:
#         result = {
#             "logs": cls.extract_logs(txn),
#             "cost": cls.extract_cost(txn),
#             "status": cls.extract_status(txn, is_app),
#             "messages": cls.extract_messages(txn, is_app),
#             "ldeltas": cls.extract_local_deltas(txn),
#             "gdelta": cls.extract_global_delta(txn),
#             "lines": cls.extract_lines(txn, is_app),
#             "trace": cls.extract_trace(txn, is_app),
#         }

#         result["bbr"] = DryRunResults.scrape(result["trace"], result["lines"])

#         return result


class DryRunEncoder:
    """Encoding utilities for dry run executions and results"""

    @classmethod
    def encode_args(
        cls,
        args: Sequence[PyTypes],
        abi_types: Optional[List[EncodingType]] = None,
        validation: bool = True,
    ) -> List[ArgType]:
        """
        Encoding convention for Black Box Testing.

        * Assumes int's are uint64 and encodes them as such
        * Leaves str's alone

        Arguments:
            args - the dry-run arguments to be encoded

            abi_types (optional) - When present this list needs to be the same length as `args`.
                When `None` is supplied as the abi_type, the corresponding element of `args` is not encoded.

            validation (optional) - This should usually be left `True` which
                ensures that -in the case of ABI typing- the number of types is
                exactly the number of args. However, in the case that the 0'th argument
                already includes the method selector, `validation` can be set `False`
                which allows the automatic prepending of `None` to the ABI types list.
        """
        a_len = len(args)
        if abi_types:
            t_len = len(abi_types)
            if validation:
                assert (
                    a_len == t_len
                ), f"mismatch between args (length={a_len}) and abi_types (length={t_len})"
            elif a_len > t_len:
                abi_types = abi_types + [None] * (a_len - t_len)

        if a_len <= MAX_APP_ARG_LIMIT:
            return [
                cls._encode_arg(a, i, abi_types[i] if abi_types else None)
                for i, a in enumerate(args)
            ]

        assert (
            abi_types
        ), f"for non-ABI app calls, there is no specification for encoding more than {MAX_APP_ARG_LIMIT} arguments. But encountered an app call attempt with {a_len} arguments"

        final_index = MAX_APP_ARG_LIMIT - 1
        simple_15 = [
            cls._encode_arg(a, i, abi_types[i])
            for i, a in enumerate(args)
            if i < final_index
        ]
        jammed_in = cls._encode_arg(
            args[final_index:],
            final_index,
            abi_type=abi.TupleType(abi_types[final_index:]),
        )
        return simple_15 + [jammed_in]

    @classmethod
    def hex0x(cls, x) -> str:
        return f"0x{cls.hex(x)}"

    @classmethod
    def hex(cls, out: Union[int, str]) -> str:
        """
        Encoding convention for Black Box Testing.

        * Assumes int's are uint64
        * Assumes everything else is a str
        * Encodes them into hex str's
        """
        cls._partial_encode_assert(out, None)
        return cast(bytes, cls._to_bytes(out)).hex()

    @classmethod
    def _to_bytes(
        cls, x: Union[int, str, bytes], only_attempt_int_conversion=False
    ) -> Union[int, str, bytes]:
        """
        NOTE: When only_attempt_int_conversion=False the output is guaranteed to be `bytes` (when no error)
        """
        if isinstance(x, bytes):
            return x

        is_int = isinstance(x, int)
        if only_attempt_int_conversion and not is_int:
            return x

        return (
            cast(int, x).to_bytes(8, "big") if is_int else bytes(cast(str, x), "utf-8")
        )

    @classmethod
    def _encode_arg(
        cls, arg: PyTypes, idx: int, abi_type: EncodingType
    ) -> Union[str, bytes]:
        partial = cls._partial_encode_assert(
            arg, abi_type, f"problem encoding arg ({arg!r}) at index ({idx})"
        )
        if partial is not None:
            return cast(bytes, partial)

        # BELOW:
        # bytes -> bytes
        # int -> bytes
        # str -> str
        return cast(
            Union[str, bytes],
            cls._to_bytes(
                cast(Union[int, str, bytes], arg), only_attempt_int_conversion=True
            ),
        )

    @classmethod
    def _partial_encode_assert(
        cls, arg: PyTypes, abi_type: EncodingType, msg: str = ""
    ) -> Optional[bytes]:
        """
        When have an `abi_type` is present, attempt to encode `arg` accordingly (returning `bytes`)
        ELSE: assert the type is one of `(bytes, int, str)` returning `None`
        """
        if abi_type:
            try:
                return cast(abi.ABIType, abi_type).encode(arg)
            except Exception as e:
                raise AssertionError(
                    f"{msg +': ' if msg else ''}can't handle arg [{arg!r}] of type {type(arg)} and abi-type {abi_type}: {e}"
                )
        assert isinstance(
            arg, (bytes, int, str)
        ), f"{msg +': ' if msg else ''}can't handle arg [{arg!r}] of type {type(arg)}"
        if isinstance(arg, int):
            assert arg >= 0, f"can't handle negative arguments but was given {arg}"
        return None


class DryRunExecutor:
    """Methods to package up and kick off dry run executions

    When executing an A.B.I. compliant dry-run specify `abi_argument_types` as well as an `abi_return_type`:
       * `abi_argument_types` are handed off to the `DryRunEncoder` for encoding purposes
       * `abi_return_type` is given the `DryRunInspector`'s resulting from execution for ABI-decoding into Python
    """

    # `CREATION_APP_CALL` and `EXISTING_APP_CALL` are enum-like constants used to denote whether a dry run
    # execution will simulate calling during on-creation vs post-creation.
    # In the default case that a dry run is executed without a provided application id (aka `index`), the `index`
    # supplied will be:
    # * `CREATION_APP_CALL` in the case of `is_app_create == True`
    # * `EXISTING_APP_CALL` in the case of `is_app_create == False`
    CREATION_APP_CALL: Final[int] = 0
    EXISTING_APP_CALL: Final[int] = 42

    SUGGESTED_PARAMS = SuggestedParams(int(1000), int(1), int(100), "", flat_fee=True)

    @classmethod
    def dryrun_app(
        cls,
        algod: AlgodClient,
        teal: str,
        args: Sequence[PyTypes],
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        sender: Optional[str] = None,
        sp: Optional[SuggestedParams] = None,
        index: Optional[int] = None,
        local_schema: Optional[StateSchema] = None,
        global_schema: Optional[StateSchema] = None,
        approval_program: Optional[str] = None,
        clear_program: Optional[str] = None,
        app_args: Optional[Sequence[Union[str, int]]] = None,
        accounts: Optional[List[str]] = None,
        foreign_apps: Optional[List[str]] = None,
        foreign_assets: Optional[List[str]] = None,
        note: Optional[str] = None,
        lease: Optional[str] = None,
        rekey_to: Optional[str] = None,
        extra_pages: Optional[int] = None,
        dryrun_accounts: List[DryRunAccountType] = [],
    ) -> "DryRunInspector":
        """
        Execute a dry run to simulate an app call using provided:

            * algod
            * teal program for the approval (or clear in the case `on_complete=OnComplete.ClearStateOC`)
            * args - the application arguments as Python types
            * abi_argument_types - ABI types of the arguments, in the case of an ABI method call
            * abi_return_type - the ABI type returned, in the case of an ABI method call
            * is_app_create to indicate whether or not to simulate an app create call
            * on_complete - the OnComplete that should be provided in the app call transaction

        Additional application call transaction parameters can be provided as well
        """
        return cls.execute_one_dryrun(
            algod,
            teal,
            args,
            ExecutionMode.Application,
            abi_method_signature=abi_method_signature,
            omit_method_selector=omit_method_selector,
            validation=validation,
            txn_params=cls.transaction_params(
                sender=ZERO_ADDRESS if sender is None else sender,
                sp=cls.SUGGESTED_PARAMS if sp is None else sp,
                note=note,
                lease=lease,
                rekey_to=rekey_to,
                index=(
                    (cls.CREATION_APP_CALL if is_app_create else cls.EXISTING_APP_CALL)
                    if index is None
                    else index
                ),
                on_complete=on_complete,
                local_schema=local_schema,
                global_schema=global_schema,
                approval_program=approval_program,
                clear_program=clear_program,
                app_args=app_args,
                accounts=accounts,
                foreign_apps=foreign_apps,
                foreign_assets=foreign_assets,
                extra_pages=extra_pages,
            ),
            accounts=dryrun_accounts,
        )

    @classmethod
    def dryrun_logicsig(
        cls,
        algod: AlgodClient,
        teal: str,
        args: Sequence[PyTypes],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        sender: str = ZERO_ADDRESS,
        sp: Optional[SuggestedParams] = None,
        receiver: Optional[str] = None,
        amt: Optional[int] = None,
        close_remainder_to: Optional[str] = None,
        note: Optional[str] = None,
        lease: Optional[str] = None,
        rekey_to: Optional[str] = None,
    ) -> "DryRunInspector":
        return cls.execute_one_dryrun(
            algod,
            teal,
            args,
            ExecutionMode.Signature,
            abi_method_signature=abi_method_signature,
            omit_method_selector=omit_method_selector,
            validation=validation,
            txn_params=cls.transaction_params(
                sender=ZERO_ADDRESS if sender is None else sender,
                sp=cls.SUGGESTED_PARAMS if sp is None else sp,
                note=note,
                lease=lease,
                rekey_to=rekey_to,
                receiver=ZERO_ADDRESS if receiver is None else receiver,
                amt=0 if amt is None else amt,
                close_remainder_to=close_remainder_to,
            ),
        )

    @classmethod
    def dryrun_app_pair_on_sequence(
        cls,
        algod: AlgodClient,
        teal_and_method1: TealAndMethodType,
        teal_and_method2: TealAndMethodType,
        inputs: List[Sequence[PyTypes]],
        *,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        dryrun_accounts: List[DryRunAccountType] = [],
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
    ) -> Tuple[Sequence["DryRunInspector"], Sequence["DryRunInspector"]]:
        return tuple(  # type: ignore
            cls.dryrun_multiapps_on_sequence(
                algod=algod,
                multi_teal_method_pairs=[teal_and_method1, teal_and_method2],
                inputs=inputs,
                is_app_create=is_app_create,
                on_complete=on_complete,
                dryrun_accounts=dryrun_accounts,
                omit_method_selector=omit_method_selector,
                validation=validation,
            )
        )

    @classmethod
    def dryrun_multiapps_on_sequence(
        cls,
        algod: AlgodClient,
        multi_teal_method_pairs: List[TealAndMethodType],
        inputs: List[Sequence[PyTypes]],
        *,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        dryrun_accounts: List[DryRunAccountType] = [],
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
    ) -> List[Sequence["DryRunInspector"]]:
        def runner(teal_method_pair):
            teal = teal_method_pair[0]
            abi_method = None
            if len(teal_method_pair) > 1:
                abi_method = teal_method_pair[1]

            return cls.dryrun_app_on_sequence(
                algod=algod,
                teal=teal,
                inputs=inputs,
                abi_method_signature=abi_method,
                omit_method_selector=omit_method_selector,
                validation=validation,
                is_app_create=is_app_create,
                on_complete=on_complete,
                dryrun_accounts=dryrun_accounts,
            )

        return list(map(runner, multi_teal_method_pairs))

    @classmethod
    def dryrun_app_on_sequence(
        cls,
        algod: AlgodClient,
        teal: str,
        inputs: List[Sequence[PyTypes]],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        dryrun_accounts: List[DryRunAccountType] = [],
    ) -> List["DryRunInspector"]:
        # TODO: handle txn_params
        return list(
            map(
                lambda args: cls.dryrun_app(
                    algod=algod,
                    teal=teal,
                    args=args,
                    abi_method_signature=abi_method_signature,
                    omit_method_selector=omit_method_selector,
                    validation=validation,
                    is_app_create=is_app_create,
                    on_complete=on_complete,
                    dryrun_accounts=dryrun_accounts,
                ),
                inputs,
            )
        )

    @classmethod
    def dryrun_logicsig_on_sequence(
        cls,
        algod: AlgodClient,
        teal: str,
        inputs: List[Sequence[PyTypes]],
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
    ) -> List["DryRunInspector"]:
        # TODO: handle txn_params
        return list(
            map(
                lambda args: cls.dryrun_logicsig(
                    algod=algod,
                    teal=teal,
                    args=args,
                    abi_method_signature=abi_method_signature,
                    omit_method_selector=omit_method_selector,
                    validation=validation,
                ),
                inputs,
            )
        )

    @classmethod
    def execute_one_dryrun(
        cls,
        algod: AlgodClient,
        teal: str,
        args: Sequence[PyTypes],
        mode: ExecutionMode,
        *,
        abi_method_signature: Optional[str] = None,
        omit_method_selector: Optional[bool] = False,
        validation: bool = True,
        txn_params: dict = {},
        accounts: List[DryRunAccountType] = [],
        verbose: bool = False,
    ) -> "DryRunInspector":
        assert (
            len(ExecutionMode) == 2
        ), f"assuming only 2 ExecutionMode's but have {len(ExecutionMode)}"
        assert mode in ExecutionMode, f"unknown mode {mode} of type {type(mode)}"
        is_app = mode == ExecutionMode.Application

        abi_argument_types: Optional[List[EncodingType]] = None
        abi_return_type: Optional[abi.ABIType] = None
        if abi_method_signature:
            """
            Try to do the right thing.
            When `omit_method_selector is False`:
                * if provided with the same number of args as expected arg types
                    --> prepend `None` to the types and `selector` to args
                * if provided with |arg types| + 1 args
                    --> assert that `args[0] == selector`
                * otherwise
                    --> there is a cardinality mismatch, so fail
            When `omit_method_selector is True`:
                * if provided with the same number of args as expected arg types
                    --> good to go
                * if provided with |arg types| + 1 args
                    --> assert that `args[0] == selector` but DROP it from the args
                * otherwise
                    --> there is a cardinality mismatch, so fail
            """
            method = abi.Method.from_signature(abi_method_signature)
            selector = method.get_selector()
            abi_argument_types = [a.type for a in method.args]

            if validation:
                args = list(args)
                if len(args) == len(abi_argument_types):
                    if not omit_method_selector:
                        # the method selector is not abi-encoded, hence its abi-type is set to None
                        abi_argument_types = [None] + abi_argument_types  # type: ignore
                        args = [selector] + args

                elif len(args) == len(abi_argument_types) + 1:
                    assert (
                        args[0] == selector
                    ), f"{args[0]=} should have been the {selector=}"

                    if omit_method_selector:
                        args = args[1:]
                    else:
                        abi_argument_types = [None] + abi_argument_types  # type: ignore

                else:
                    raise AssertionError(
                        f"{len(args)=} is incompatible with {len(method.args)=}: LEFT should be equal or exactly RIGHT + 1"
                    )
            elif not omit_method_selector:
                abi_argument_types = [None] + abi_argument_types  # type: ignore

            args = tuple(args)

            if method.returns.type != abi.Returns.VOID:
                abi_return_type = cast(abi.ABIType, method.returns.type)

        encoded_args = DryRunEncoder.encode_args(
            args, abi_types=abi_argument_types, validation=validation
        )

        dryrun_req: DryrunRequest
        if is_app:
            dryrun_req = DryRunHelper.singleton_app_request(
                teal, encoded_args, txn_params, accounts
            )
        else:
            dryrun_req = DryRunHelper.singleton_logicsig_request(
                teal, encoded_args, txn_params
            )
        if verbose:
            print(f"{cls}::execute_one_dryrun(): {dryrun_req=}")
        dryrun_resp = algod.dryrun(dryrun_req)
        if verbose:
            print(f"{cls}::execute_one_dryrun(): {dryrun_resp=}")
        return DryRunInspector.from_single_response(
            dryrun_resp, args, encoded_args, abi_type=cast(abi.ABIType, abi_return_type)
        )

    @classmethod
    def transaction_params(
        cls,
        *,
        # generic:
        sender: Optional[str] = None,
        sp: Optional[SuggestedParams] = None,
        note: Optional[str] = None,
        lease: Optional[str] = None,
        rekey_to: Optional[str] = None,
        # payments:
        receiver: Optional[str] = None,
        amt: Optional[int] = None,
        close_remainder_to: Optional[str] = None,
        # apps:
        index: Optional[int] = None,
        on_complete: Optional[OnComplete] = None,
        local_schema: Optional[StateSchema] = None,
        global_schema: Optional[StateSchema] = None,
        approval_program: Optional[str] = None,
        clear_program: Optional[str] = None,
        app_args: Optional[Sequence[Union[str, int]]] = None,
        accounts: Optional[List[str]] = None,
        foreign_apps: Optional[List[str]] = None,
        foreign_assets: Optional[List[str]] = None,
        extra_pages: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Returns a `dict` with keys the same as method params, after removing all `None` values
        """
        params = dict(
            sender=sender,
            sp=sp,
            note=note,
            lease=lease,
            rekey_to=rekey_to,
            receiver=receiver,
            amt=amt,
            close_remainder_to=close_remainder_to,
            index=index,
            on_complete=on_complete,
            local_schema=local_schema,
            global_schema=global_schema,
            approval_program=approval_program,
            clear_program=clear_program,
            app_args=app_args,
            accounts=accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
            extra_pages=extra_pages,
        )
        return {k: v for k, v in params.items() if v is not None}


class ABIContractExecutor:
    """Execute an ABI Contract via Dry Run"""

    def __init__(
        self,
        teal: str,
        contract: str,
        argument_strategy: Optional[Type[ABIStrategy]] = RandomABIStrategy,
        dry_runs: int = 1,
        handle_selector: bool = False,
    ):
        """
        teal - The program to run

        contract - ABI Contract JSON

        argument_strategy (optional) - strategy for generating arguments

        dry_runs (default=1) - the number of dry runs to run
            (generates different inputs each time)

        handle_selector - usually we'll want to let `DryRunExecutor.execute_one_dryrun()`
            handle adding the method selector so this param
            should _probably_ be left False. But when set True, when providing `inputs`
            ensure that the 0'th argument for method calls is the selector.
            And when set True, when NOT providing `inputs`, the selector arg
            at index 0 will be added automatically.
        """
        self.program = teal
        self.contract: abi.Contract = abi.Contract.from_json(contract)
        self.argument_strategy: Optional[Type[ABIStrategy]] = argument_strategy
        self.dry_runs = dry_runs
        self.handle_selector = handle_selector

    def method_signature(self, method: Optional[str]) -> Optional[str]:
        """Returns None, for a bare app call (method=None signals this)"""
        if not method:
            return None

        return self.contract.get_method_by_name(method).get_signature()

    def argument_types(self, method: Optional[str] = None) -> List[abi.ABIType]:
        """
        Argument types (excluding selector)
        """
        if not method:
            return []

        return [
            cast(abi.ABIType, arg.type)
            for arg in self.contract.get_method_by_name(method).args
        ]

    def generate_inputs(self, method: Optional[str]) -> List[Sequence[PyTypes]]:
        """
        Generates inputs appropriate for bare app call,
        AND appropirate for method calls, if put starting at index = 1.
        Uses available argument_strategy.
        """
        assert (
            self.argument_strategy
        ), "cannot generate inputs without an argument_strategy"

        if not method:
            # bare calls receive no arguments
            return [tuple() for _ in range(self.dry_runs)]

        arg_types = self.argument_types(method)
        prefix = []
        if self.handle_selector and method:
            prefix = [self.contract.get_method_by_name(method).get_selector()]

        def gen_args():
            return tuple(
                prefix
                + [self.argument_strategy(arg_type).get() for arg_type in arg_types]
            )

        return [gen_args() for _ in range(self.dry_runs)]

    def validate_inputs(self, method: Optional[str], inputs: List[Sequence[PyTypes]]):
        """TODO: add type validation for arguments"""

        if not method:
            assert not any(
                inputs
            ), f"bare app calls require args to be empty but inputs={inputs}"
            return

        arg_types = self.argument_types(method)
        selector_if_needed: Optional[bytes] = None
        if self.handle_selector:
            selector_if_needed = self.contract.get_method_by_name(method).get_selector()

        error = None
        for i, args in enumerate(inputs):
            targs = cast(tuple, args)
            if selector_if_needed:
                pfx = f"args at index {i=}: "
                if len(targs) != 1 + len(arg_types):
                    error = f"{pfx}length {len(targs)} should include method selector and so have length 1 + {len(arg_types)}"
                    break

                if targs[0] != selector_if_needed:
                    error = f"{pfx}expected selector={selector_if_needed!r} at arg 0 but got {targs[0]!r}"
                    break

        assert not error, error

    def dry_run_on_sequence(
        self,
        algod: AlgodClient,
        method: Optional[str] = None,
        is_app_create: bool = False,
        on_complete: OnComplete = OnComplete.NoOpOC,
        inputs: Optional[List[Sequence[PyTypes]]] = None,
        *,
        validation: bool = True,
        dryrun_accounts: List[DryRunAccountType] = [],
    ) -> List["DryRunInspector"]:
        """ARC-4 Compliant Dry Run
        When inputs aren't provided, you should INSTEAD SHOULD HAVE PROVIDED
        an `argument_strategy` upon construction.
        When inputs ARE provided, don't include the method selector as that
        is automatically generated.
        """
        # TODO: handle txn_params

        if inputs is None:
            inputs = self.generate_inputs(method)

        if validation:
            self.validate_inputs(method, inputs)

        return DryRunExecutor.dryrun_app_on_sequence(
            algod,
            self.program,
            inputs,
            abi_method_signature=self.method_signature(method),
            omit_method_selector=False,
            validation=validation,
            is_app_create=is_app_create,
            on_complete=on_complete,
            dryrun_accounts=dryrun_accounts,
        )
