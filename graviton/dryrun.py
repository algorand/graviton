import base64
import binascii
from contextlib import redirect_stdout
from dataclasses import dataclass
import io
import string
from typing import Any, Dict, List, Optional, Union

from algosdk.future import transaction
from algosdk.encoding import encode_address, msgpack_encode
from algosdk.v2client.models import (
    DryrunRequest,
    DryrunSource,
    Application,
    ApplicationParams,
    ApplicationStateSchema,
    Account,
    TealKeyValue,
)


ZERO_ADDRESS = encode_address(bytes(32))
PRINTABLE = frozenset(string.printable)


@dataclass
class LSig:
    """Logic Sig program parameters"""

    args: Optional[List[bytes]] = None


@dataclass
class App:
    """Application program parameters"""

    creator: str = ZERO_ADDRESS
    round: Optional[int] = None
    app_idx: int = 0
    on_complete: int = 0
    args: Optional[List[Union[bytes, str]]] = None
    accounts: Optional[List[Union[str, Account]]] = None
    global_state: Optional[List[TealKeyValue]] = None


# ### LIGHTWEIGHT ASSERTIONS FOR RE-USE ### #
def _msg_if(msg):
    return "" if msg is None else f": {msg}"


def _fail(msg):
    assert False, msg


def _assert_in(status, msgs, msg=None, enforce=True):
    ok = status in msgs
    result = None
    if not ok:
        result = f"{status} should be in {msgs}" + _msg_if(msg)
        if enforce:
            assert status in msgs, result

    return ok, result


def assert_pass(txn_index, msg, txns_res):
    assert_status("PASS", txn_index, msg, txns_res)


def assert_reject(txn_index, msg, txns_res):
    assert_status("REJECT", txn_index, msg, txns_res)


def assert_status(status, txn_index, msg, txns_res, enforce=True):
    if txn_index is not None and (txn_index < 0 or txn_index >= len(txns_res)):
        _fail(f"txn index {txn_index} is out of range [0, {len(txns_res)})")

    assert_all = True
    all_msgs = []
    if status == "REJECT":
        assert_all = False

    for idx, txn_res in enumerate(txns_res):
        # skip if txn_index is set
        if txn_index is not None and idx != txn_index:
            continue

        msgs = []
        if (
            "logic-sig-messages" in txn_res
            and txn_res["logic-sig-messages"] is not None
            and len(txn_res["logic-sig-messages"]) > 0
        ):
            msgs = txn_res["logic-sig-messages"]
        elif (
            "app-call-messages" in txn_res
            and txn_res["app-call-messages"] is not None
            and len(txn_res["app-call-messages"]) > 0
        ):
            msgs = txn_res["app-call-messages"]
        else:
            _fail("no messages from dryrun")
        if assert_all or idx == txn_index:
            _assert_in(status, msgs, msg=msg)
        all_msgs.extend(msgs)

    if not assert_all:
        return _assert_in(status, all_msgs, msg=msg, enforce=enforce)

    return True, None


def assert_error(drr, contains=None, txn_index=None, msg=None, enforce=True):
    error = DryRunHelper.find_error(drr, txn_index=txn_index)
    ok = bool(error)
    if not ok:  # the expected error did NOT occur
        result = f"expected truthy error but got {error}" + _msg_if(msg)
        if enforce:
            assert error, result
        return ok, result
    # got here? Must have error
    if contains is not None:
        return _assert_in(contains, error, enforce=enforce)

    return True, None


def assert_no_error(drr, txn_index=None, msg=None, enforce=True):
    error = DryRunHelper.find_error(drr, txn_index=txn_index)
    ok = not bool(error)
    result = None
    if not ok:
        result = f"{msg}: {error}" + _msg_if(msg)
        if enforce:
            assert not error, result

    return ok, result


def assert_global_state_contains(delta_value, txn_index, txns_res, msg=None):
    if txn_index is not None and (txn_index < 0 or txn_index >= len(txns_res)):
        _fail(f"txn index {txn_index} is out of range [0, {len(txns_res)})")

    found = False
    all_global_deltas = []
    for idx, txn_res in enumerate(txns_res):
        # skip if txn_index is set
        if txn_index is not None and idx != txn_index:
            continue
        if (
            "global-delta" in txn_res
            and txn_res["global-delta"] is not None
            and len(txn_res["global-delta"]) > 0
        ):
            found = DryRunHelper.find_delta_value(txn_res["global-delta"], delta_value)
            if not found and idx == txn_index:
                msg = (
                    msg
                    if msg is not None
                    else f"{delta_value} not found in {txn_res['global-delta']}"
                )
                _fail(msg)
            if found:
                break
            all_global_deltas.extend(txn_res["global-delta"])
        elif idx == txn_index:
            _fail("no global state from dryrun")

    if not found:
        msg = (
            msg
            if msg is not None
            else f"{delta_value} not found in any of {all_global_deltas}"
        )
        _fail(msg)


def assert_local_state_contains(addr, delta_value, txn_index, txns_res, msg=None):
    if txn_index is not None and (txn_index < 0 or txn_index >= len(txns_res)):
        _fail(f"txn index {txn_index} is out of range [0, {len(txns_res)})")

    found = False
    all_local_deltas = []
    for idx, txn_res in enumerate(txns_res):
        # skip if txn_index is set
        if txn_index is not None and idx != txn_index:
            continue
        if (
            "local-deltas" in txn_res
            and txn_res["local-deltas"] is not None
            and len(txn_res["local-deltas"]) > 0
        ):
            addr_found = False
            for local_delta in txn_res["local-deltas"]:
                addr_found = False
                if local_delta["address"] == addr:
                    addr_found = True
                    found = DryRunHelper.find_delta_value(
                        local_delta["delta"], delta_value
                    )
                    if not found and idx == txn_index:
                        msg = (
                            msg
                            if msg is not None
                            else f"{delta_value} not found in {local_delta['delta']}"
                        )
                        _fail(msg)
                    if found:
                        break
                    all_local_deltas.extend(local_delta["delta"])
            if not addr_found and idx == txn_index:
                _fail(f"no address {addr} in local states from dryrun")
        elif idx == txn_index:
            _fail("no local states from dryrun")

    if not found:
        msg = (
            msg
            if msg is not None
            else f"{delta_value} not found in any of {all_local_deltas}"
        )
        _fail(msg)


class DryrunTestCaseMixin:
    """
    Mixin class for unittest.TestCase

    Expects self.algo_client to be initialized in TestCase.setUp
    """

    def assertPass(
        self,
        prog_drr_txns,
        lsig=None,
        app=None,
        sender=ZERO_ADDRESS,
        txn_index=None,
        msg=None,
    ):
        """
        Asserts that all programs pass.
        By default it uses logic sig mode with args passed in lsig object.
        If app is set then application call is made

        Args:
            prog_drr_txns (bytes, str, dict, list): program to run, dryrun response object or list of transactions
            lsig (dict, LSig): logic sig program additional parameters
            app (dict, App): app program additional parameters
            sender (str): txn sender
            txn_index (int): txn result index to assert in

        Raises:
            unittest.TestCase.failureException: if not passed
            TypeError: program is not bytes or str
        """
        txns_res = self._checked_request(prog_drr_txns, lsig, app, sender)
        assert_pass(txn_index, msg, txns_res)

    def assertReject(
        self,
        prog_drr_txns,
        lsig=None,
        app=None,
        sender=ZERO_ADDRESS,
        txn_index=None,
        msg=None,
    ):
        """
        Asserts any program is rejected.
        By default it uses logic sig mode with args passed in lsig object.
        If app is set then application call is made

        Args:
            prog_drr_txns (bytes, str, dict, list): program to run, dryrun response object or list of transactions
            lsig (dict, LSig): logic sig program additional parameters
            app (dict, App): app program additional parameters
            sender (str): txn sender
            txn_index (int): txn result index to assert in

        Raises:
            unittest.TestCase.failureException: if not passed
            TypeError: program is not bytes or str
        """
        txns_res = self._checked_request(prog_drr_txns, lsig, app, sender)
        assert_reject(txn_index, msg, txns_res)

    def assertStatus(
        self,
        prog_drr_txns,
        status,
        lsig=None,
        app=None,
        sender=ZERO_ADDRESS,
        txn_index=None,
        msg=None,
    ):
        """
        Asserts that program completes with the status.
        By default it uses logic sig mode with args passed in lsig object.
        If app is set then application call is made

        Args:
            prog_drr_txns (bytes, str, dict, list): program to run, dryrun response object or list of transactions
            status (str): status to assert
            lsig (dict, LSig): logic sig program additional parameters
            app (dict, App): app program additional parameters
            sender (str): txn sender
            txn_index (int): txn result index to assert in

        Raises:
            unittest.TestCase.failureException (AssetionException): if not passed
            TypeError: program is not bytes or str
        """
        txns_res = self._checked_request(prog_drr_txns, lsig, app, sender)
        assert_status(status, txn_index, msg, txns_res)

    def assertNoError(
        self,
        prog_drr_txns,
        lsig=None,
        app=None,
        sender=ZERO_ADDRESS,
        txn_index=None,
        msg=None,
    ):
        """
        Asserts that there are no errors.
        for example, compilation errors or application state initialization errors.
        By default it uses logic sig mode with args passed in lsig object.
        If app is set then application call is made

        Args:
            prog_drr_txns (bytes, str, dict, list): program to run, dryrun response object or list of transactions
            lsig (dict, LSig): logic sig program additional parameters
            app (dict, App): app program additional parameters
            sender (str): txn sender
            txn_index (int): txn result index to assert in

        Raises:
            unittest.TestCase.failureException (AssetionException): if not passed
            TypeError: program is not bytes or str
        """
        drr = self._dryrun_request(prog_drr_txns, lsig, app, sender)
        assert_no_error(drr, txn_index=txn_index, msg=msg)

    def assertError(
        self,
        prog_drr_txns,
        contains=None,
        lsig=None,
        app=None,
        sender=ZERO_ADDRESS,
        txn_index=None,
        msg=None,
    ):
        """
        Asserts that there are no errors.
        for example, compilation errors or application state initialization errors.
        By default it uses logic sig mode with args passed in lsig object.
        If app is set then application call is made

        Args:
            prog_drr_txns (bytes, str, dict, list): program to run, dryrun response object or list of transactions
            lsig (dict, LSig): logic sig program additional parameters
            app (dict, App): app program additional parameters
            sender (str): txn sender
            txn_index (int): txn result index to assert in

        Raises:
            unittest.TestCase.failureException (AssetionException): if not passed
            TypeError: program is not bytes or str
        """

        drr = self._dryrun_request(prog_drr_txns, lsig, app, sender)
        assert_error(drr, contains=contains, txn_index=txn_index, msg=msg)

    def assertGlobalStateContains(
        self,
        prog_drr_txns,
        delta_value,
        app=None,
        sender=ZERO_ADDRESS,
        txn_index=None,
        msg=None,
    ):
        """
        Asserts that execution of the program has this global delta value

        Args:
            prog_drr_txns (bytes, str, dict, list): program to run, dryrun response object or list of transactions
            delta_value (dict): value to assert

        Raises:
            unittest.TestCase.failureException: if not passed
            TypeError: program is not bytes or str
        """

        txns_res = self._checked_request(
            prog_drr_txns, lsig=None, app=app, sender=sender
        )
        assert_global_state_contains(delta_value, txn_index, txns_res, msg=msg)

    def assertLocalStateContains(
        self,
        prog_drr_txns,
        addr,
        delta_value,
        app=None,
        sender=ZERO_ADDRESS,
        txn_index=None,
        msg=None,
    ):
        """
        Asserts that execution of the program has this global delta value

        Args:
            prog_drr_txns (bytes, str, dict, list): program to run, dryrun response object or list of transactions
            addr (str): account
            delta_value (dict): value to assert

        Raises:
            unittest.TestCase.failureException: if not passed
            TypeError: program is not bytes or str
        """

        txns_res = self._checked_request(
            prog_drr_txns, lsig=None, app=app, sender=sender
        )
        assert_local_state_contains(addr, delta_value, txn_index, txns_res, msg=msg)

    def dryrun_request(self, program, lsig=None, app=None, sender=ZERO_ADDRESS):
        """
        Helper function for creation DryrunRequest and making the REST request
        from program source or compiled bytes

        Args:
            program (bytes, str): program to use as a source
            lsig (dict, LSig): logic sig program additional parameters
            app (dict, App): app program additional parameters
            sender (str): txn sender

        Returns:
            dict: dryrun response object

        Raises:
            TypeError: program is not bytes or str
        """
        drr = DryRunHelper._deprecated_dryrun(program, lsig, app, sender)
        return self.algo_client.dryrun(drr)

    def dryrun_request_from_txn(self, txns, app):
        """
        Helper function for creation DryrunRequest and making the REST request

        Args:
            txns (list): list of transaction to run as a group
            app (dict, App): app program additional parameters. Only app.round and app.accounts are used.

        Returns:
            dict: dryrun response object

        Raises:
            TypeError: program is not bytes or str
        """

        if app is not None:
            if not isinstance(app, App) and not isinstance(app, dict):
                raise ValueError("app must be a dict or App")
            if isinstance(app, dict):
                app = App(**app)

        rnd = None
        accounts = None
        apps = []
        if app is not None:
            if app.round is not None:
                rnd = app.round
            if app.accounts is not None:
                accounts = app.accounts
                for acc in accounts:
                    if acc.created_apps:
                        apps.extend(acc.created_apps)

        drr = DryrunRequest(
            txns=txns,
            accounts=accounts,
            round=rnd,
            apps=apps,
        )
        return self.algo_client.dryrun(drr)

    @staticmethod
    def default_address():
        """Helper function returning default zero addr"""
        return ZERO_ADDRESS

    def _dryrun_request(self, prog_drr_txns, lsig, app, sender):
        """
        Helper function to make a dryrun request
        """
        if isinstance(prog_drr_txns, dict):
            drr = prog_drr_txns
        elif isinstance(prog_drr_txns, list):
            drr = self.dryrun_request_from_txn(prog_drr_txns, app)
        else:
            drr = self.dryrun_request(prog_drr_txns, lsig, app, sender)
        return drr

    def _checked_request(self, prog_drr_txns, lsig=None, app=None, sender=ZERO_ADDRESS):
        """
        Helper function to make a dryrun request and perform basic validation
        """
        drr = self._dryrun_request(prog_drr_txns, lsig, app, sender)
        if drr["error"]:
            _fail(f"error in dryrun response: {drr['error']}")

        if not drr["txns"]:
            _fail("empty response from dryrun")

        return drr["txns"]


class DryRunHelper:
    """Utility functions for dryrun"""

    @classmethod
    def singleton_logicsig_request(
        cls, program: str, args: List[bytes], txn_params: Dict[str, Any]
    ):
        return cls.dryrun_request(program, LSig(args=args), txn_params)

    @classmethod
    def singleton_app_request(
        cls, program: str, args: List[Union[bytes, str]], txn_params: Dict[str, Any]
    ):
        return cls.dryrun_request(program, App(args=args), txn_params)

    @classmethod
    def dryrun_request(cls, program, lsig_or_app, txn_params):
        assert isinstance(
            lsig_or_app, (LSig, App)
        ), f"Cannot handle {lsig_or_app} of type {type(lsig_or_app)}"
        is_app = isinstance(lsig_or_app, App)
        if is_app:
            return cls._app_request(program, lsig_or_app, txn_params)

        return cls._lsig_request(program, lsig_or_app, txn_params)

    @classmethod
    def _app_request(cls, program, app, txn_params):
        """TODO: out to be able to stop delegating at tis point"""
        run_mode = cls._get_run_mode(app)
        enriched = cls._prepare_app(app)
        txn = transaction.ApplicationCallTxn(**txn_params)
        return cls._prepare_app_source_request(program, enriched, run_mode, txn)

    @classmethod
    def _lsig_request(cls, program, lsig, txn_params):
        """TODO: out to be able to stop delegating at tis point"""
        enriched = cls._prepare_lsig(lsig)
        txn = transaction.PaymentTxn(**txn_params)
        return cls._prepare_lsig_source_request(program, enriched, txn)

    @classmethod
    def _deprecated_dryrun(cls, program, lsig=None, app=None, sender=ZERO_ADDRESS):
        """
        Helper function for creation DryrunRequest object from a program.
        By default it uses logic sig mode
        and if app_idx / on_complete are set then application call is made

        Args:
            program (bytes, string): program to use as a source
            lsig (dict, LSig): logic sig program additional parameters
            app (dict, App): app program additional parameters

        Returns:
            DryrunRequest: dryrun request object

        Raises:
            TypeError: program is not bytes or str
            ValueError: both lsig and app parameters provided or unknown type
        """

        if lsig is not None and app is not None:
            raise ValueError("both lsig and app not supported")

        if app and not isinstance(app, (App, dict)):
            raise ValueError("app must be a dict or App")

        if lsig and not isinstance(lsig, (LSig, dict)):
            raise ValueError("lsig must be a dict or LSig")

        if isinstance(app, dict):
            app = App(**app)
        elif isinstance(lsig, dict):
            lsig = LSig(**lsig)
        else:  # both are None
            lsig = LSig()

        if not isinstance(program, (bytes, str)):
            raise TypeError("program must be bytes or str")

        run_mode = cls._get_run_mode(app)
        is_app = run_mode != "lsig"
        lsig_or_app = app if is_app else lsig
        txn_params = cls.sample_txn_params(sender, is_app)

        if isinstance(program, str):
            return cls.dryrun_request(program, lsig_or_app, txn_params)

        assert (
            False
        ), f"this is unreachable  as far as I can tell - type(program)={type(program)} - (HAVE DEPRECATED program of type bytes)!!!"
        # del app
        # del lsig

        # # in case of bytes:
        # sources = []
        # apps = []
        # accounts = []
        # rnd = None

        # txn = (
        #     transaction.ApplicationCallTxn(**txn_params)
        #     if is_app
        #     else transaction.PaymentTxn(**txn_params)
        # )
        # if run_mode != "lsig":
        #     txns = [cls._build_appcall_signed_txn(txn, app_or_lsig)]
        #     application = cls.sample_app(sender, app_or_lsig, program)
        #     apps = [application]
        #     accounts = app_or_lsig.accounts
        #     rnd = app_or_lsig.round
        # else:
        #     txns = [cls._build_logicsig_txn(program, txn, app_or_lsig)]

        # return DryrunRequest(
        #     txns=txns,
        #     sources=sources,
        #     apps=apps,
        #     accounts=accounts,
        #     round=rnd,
        # )

    @classmethod
    def _get_run_mode(cls, app):
        run_mode = "lsig"
        if app is not None:
            on_complete = (
                app.get("on_complete") if isinstance(app, dict) else app.on_complete
            )
            run_mode = (
                "clearp"
                if on_complete == transaction.OnComplete.ClearStateOC
                else "approv"
            )
        return run_mode

    @classmethod
    def _prepare_app(cls, app):
        # TODO: This code is smelly. Make it less so.
        if isinstance(app, dict):
            app = App(**app)

        if app.app_idx is None:
            app.app_idx = 0

        if app.accounts is not None:
            accounts = []
            for acc in app.accounts:
                if isinstance(acc, str):
                    acc = Account(address=acc)
                accounts.append(acc)
            app.accounts = accounts

        return app

    @classmethod
    def _prepare_lsig(cls, lsig):
        if lsig is None:
            lsig = LSig()
        elif isinstance(lsig, dict):
            lsig = LSig(**lsig)
        return lsig

    @classmethod
    def _prepare_lsig_source_request(cls, program, lsig, txn):
        source = DryrunSource(field_name="lsig", source=program, txn_index=0)
        apps = []
        accounts = []
        rnd = None
        txns = [cls._build_logicsig_txn(program, txn, lsig)]
        sources = [source]
        return DryrunRequest(
            txns=txns,
            sources=sources,
            apps=apps,
            accounts=accounts,
            round=rnd,
        )

    @classmethod
    def _prepare_app_source_request(cls, program, app, run_mode, txn):
        sender = txn.sender
        source = DryrunSource(field_name=run_mode, source=program, txn_index=0)
        txns = [cls._build_appcall_signed_txn(txn, app)]
        application = cls.sample_app(sender, app)
        apps = [application]
        accounts = app.accounts
        # app idx must match in sources and in apps arrays so dryrun find apps sources
        source.app_index = application.id
        rnd = app.round
        sources = [source]
        return DryrunRequest(
            txns=txns,
            sources=sources,
            apps=apps,
            accounts=accounts,
            round=rnd,
        )

    @staticmethod
    def _build_logicsig_txn(program, txn, lsig):
        """
        Helper function to make LogicSigTransaction
        """
        # replacing program with an empty one is OK since it set by source
        # LogicSig does not like None/invalid programs because of validation
        program = program if isinstance(program, bytes) else b"\x01"
        logicsig = transaction.LogicSig(program, lsig.args)
        return transaction.LogicSigTransaction(txn, logicsig)

    @staticmethod
    def _build_appcall_signed_txn(txn, app):
        """
        Helper function to make SignedTransaction
        """
        txn.index = app.app_idx
        txn.on_complete = app.on_complete
        txn.app_args = app.args
        if app.accounts is not None:
            txn.accounts = [a.address for a in app.accounts]
        return transaction.SignedTransaction(txn, None)

    @classmethod
    def sample_txn_params(cls, sender: str, is_app: bool):
        sp = transaction.SuggestedParams(int(1000), int(1), int(100), "", flat_fee=True)
        if is_app:
            return dict(sender=sender, sp=sp, index=0, on_complete=0)

        return dict(sender=sender, sp=sp, receiver=sender, amt=0)

    @staticmethod
    def sample_app(sender, app, program=None):
        """
        Helper function for creation Application description for dryrun
        """
        default_app_id = 1380011588
        # dryrun ledger can't stand app idx = 0
        # and requires some non-zero if even for app create txn
        if app.app_idx == 0:
            creator = sender
            idx = default_app_id
        else:
            idx = app.app_idx
            creator = app.creator
        params = ApplicationParams(
            creator=creator,
            local_state_schema=ApplicationStateSchema(64, 64),
            global_state_schema=ApplicationStateSchema(64, 64),
            global_state=app.global_state,
        )

        if app.on_complete == transaction.OnComplete.ClearStateOC:
            params.clear_state_program = program
        else:
            params.approval_program = program

        return Application(idx, params)

    @staticmethod
    def _guess(value):
        try:
            value = base64.b64decode(value)
        except binascii.Error:
            return value

        try:
            all_print = True
            for b in value:
                if chr(b) not in PRINTABLE:
                    all_print = False
            if all_print:
                return '"' + value.decode("utf8") + '"'
            else:
                if len(value) == 32:  # address? hash?
                    return f"{encode_address(value)} ({value.hex()})"
                elif len(value) < 16:  # most likely bin number
                    return "0x" + value.hex()
                return value.hex()
        except UnicodeDecodeError:
            return value.hex()

    @classmethod
    def _format_stack(cls, stack):
        parts = []
        for item in stack:
            if item["type"] == 1:  # bytes
                item = cls._guess(item["bytes"])
            else:
                item = str(item["uint"])
            parts.append(item)
        return " ".join(parts)

    @classmethod
    def pprint(cls, drr) -> str:
        """Helper function to pretty print dryrun response"""
        f = io.StringIO()
        with redirect_stdout(f):
            if "error" in drr and drr["error"]:
                print("error:", drr["error"])
            if "txns" in drr and isinstance(drr["txns"], list):
                for idx, txn_res in enumerate(drr["txns"]):
                    msgs = []
                    trace = []
                    try:
                        msgs = txn_res["app-call-messages"]
                        trace = txn_res["app-call-trace"]
                    except KeyError:
                        try:
                            msgs = txn_res["logic-sig-messages"]
                            trace = txn_res["logic-sig-trace"]
                        except KeyError:
                            pass
                    if msgs:
                        print(f"txn[{idx}] messages:")
                        for msg in msgs:
                            print(msg)
                    if trace:
                        print(f"txn[{idx}] trace:")
                        for item in trace:
                            dis = txn_res["disassembly"][item["line"]]
                            stack = cls._format_stack(item["stack"])
                            line = "{:4d}".format(item["line"])
                            pc = "{:04d}".format(item["pc"])
                            disasm = "{:25}".format(dis)
                            stack_line = "{}".format(stack)
                            result = f"{line} ({pc}): {disasm} [{stack_line}]"
                            if "error" in item:
                                result += f" error: {item['error']}"
                            print(result)
        out = f.getvalue()
        print(out)
        return out

    @staticmethod
    def find_error(drr, txn_index=None):
        """
        Helper function to find error in dryrun response
        """
        try:
            if len(drr["error"]) > 0:
                return drr["error"]
        except (KeyError, TypeError):
            pass
        if "txns" in drr and isinstance(drr["txns"], list):
            if txn_index is not None and (
                txn_index < 0 or txn_index >= len(drr["txns"])
            ):
                return f"txn index {txn_index} is out of range [0, {len(drr['txns'])})"

            for idx, txn_res in enumerate(drr["txns"]):
                if txn_index is not None and txn_index != idx:
                    continue
                try:
                    ptype = "app"
                    trace = txn_res["app-call-trace"]
                except KeyError:
                    try:
                        ptype = "logic"
                        trace = txn_res["logic-sig-trace"]
                    except KeyError:
                        continue

                for item in trace:
                    if "error" in item:
                        error = f"{ptype} {idx} failed at line {item['line']}: {item['error']}"
                        return error

    @staticmethod
    def build_bytes_delta_value(value):
        if isinstance(value, str):
            value = value.encode("utf-8")
        return dict(
            action=1,  # set bytes
            bytes=base64.b64encode(value).decode("utf-8"),  # b64 input to string
        )

    @staticmethod
    def find_delta_value(deltas, delta_value):
        found = False
        for delta in deltas:
            try:
                if delta["key"] == delta_value["key"]:
                    value = delta["value"]
                    if value["action"] == delta_value["value"]["action"]:
                        if "uint" in delta_value["value"]:
                            if delta_value["value"]["uint"] == value["uint"]:
                                found = True
                                break
                        elif "bytes" in delta_value["value"]:
                            if delta_value["value"]["bytes"] == value["bytes"]:
                                found = True
                                break
            except KeyError:
                pass
        return found

    @staticmethod
    def save_dryrun_request(name_or_fp, req):
        """Helper function to save dryrun request

        Args:
            name_or_fp (str, file-like): filename or fp to save the request to
            req (DryrunRequest): dryrun request object to save
        """
        need_close = False
        if isinstance(name_or_fp, str):
            fp = open(name_or_fp, "wb")
            need_close = True
        else:
            fp = name_or_fp

        data = msgpack_encode(req)
        data = base64.b64decode(data)

        fp.write(data)
        if need_close:
            fp.close()
