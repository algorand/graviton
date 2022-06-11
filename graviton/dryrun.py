import base64
import binascii
from contextlib import redirect_stdout
import io
import string
from typing import Any, Dict, List, Union

from algosdk.future import transaction
from algosdk.encoding import encode_address, msgpack_encode
from algosdk.v2client.models import (
    DryrunRequest,
    DryrunSource,
    Application,
    ApplicationParams,
    ApplicationStateSchema,
    Account,
)

from . import models

PRINTABLE = frozenset(string.printable)

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


class DryRunHelper:
    """Utility functions for dryrun"""

    @classmethod
    def singleton_logicsig_request(
        cls, program: str, args: List[bytes], txn_params: Dict[str, Any]
    ):
        return cls.dryrun_request(program, models.LSig(args=args), txn_params)

    @classmethod
    def singleton_app_request(
        cls, program: str, args: List[Union[bytes, str]], txn_params: Dict[str, Any]
    ):
        creator = txn_params.get("sender")
        app_idx = txn_params.get("index")
        on_complete = txn_params.get("on_complete")
        app = models.App.factory(
            creator=creator, app_idx=app_idx, on_complete=on_complete, args=args
        )
        return cls.dryrun_request(program, app, txn_params)

    @classmethod
    def _txn_params_with_defaults(cls, txn_params: dict, for_app: bool) -> dict:
        """
        Fill `txn_params` with required fields (without modifying input)

        Universal:
            * sender (str): address of the sender
            * sp (SuggestedParams): suggested params from algod

        Non-Payement (for app):
            * index (int): index of the application to call; 0 if creating a new application
            * on_complete (OnComplete): intEnum representing what app should do on completion

        Payment (for logic sig):
            * receiver (str): address of the receiver
            * amt (int): amount in microAlgos to be sent
        """
        txn_params = {**txn_params}

        if "sender" not in txn_params:
            txn_params["sender"] = encode_address(bytes(32))

        if "sp" not in txn_params:
            txn_params["sp"] = transaction.SuggestedParams(
                int(1000), int(1), int(100), "", flat_fee=True
            )

        if for_app:
            if "index" not in txn_params:
                txn_params["index"] = 0

            if "on_complete" not in txn_params:
                txn_params["on_complete"] = transaction.OnComplete.NoOpOC
        else:
            if "receiver" not in txn_params:
                txn_params["receiver"] = encode_address(bytes(32))

            if "amt" not in txn_params:
                txn_params["amt"] = 0

        return txn_params

    @classmethod
    def dryrun_request(cls, program, lsig_or_app, txn_params):
        assert isinstance(
            lsig_or_app, (models.LSig, models.App)
        ), f"Cannot handle {lsig_or_app} of type {type(lsig_or_app)}"
        is_app = isinstance(lsig_or_app, models.App)

        txn_params = cls._txn_params_with_defaults(txn_params, for_app=is_app)

        if is_app:
            return cls._app_request(program, lsig_or_app, txn_params)

        return cls._lsig_request(program, lsig_or_app, txn_params)

    @classmethod
    def _app_request(cls, program, app, txn_params):
        """TODO: ought to be able to stop delegating at this point"""
        run_mode = models.get_run_mode(app)
        enriched = cls._prepare_app(app)
        txn = transaction.ApplicationCallTxn(**txn_params)
        return cls._prepare_app_source_request(program, enriched, run_mode, txn)

    @classmethod
    def _lsig_request(cls, program, lsig, txn_params):
        """TODO: ought to be able to stop delegating at this point"""
        enriched = cls._prepare_lsig(lsig)
        txn = transaction.PaymentTxn(**txn_params)
        return cls._prepare_lsig_source_request(program, enriched, txn)

    @classmethod
    def _prepare_app(cls, app):
        # TODO: This code is smelly. Make it less so.
        if isinstance(app, dict):
            app = models.App(**app)

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
            lsig = models.LSig()
        elif isinstance(lsig, dict):
            lsig = models.LSig(**lsig)
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
