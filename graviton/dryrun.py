from copy import copy
import string
from typing import Any, Dict, List

from algosdk import transaction
from algosdk.encoding import encode_address
from algosdk.v2client.models import (
    DryrunRequest,
    DryrunSource,
    Application,
    ApplicationParams,
    ApplicationStateSchema,
    Account,
)

from graviton import models
from graviton.models import ArgType, DryRunAccountType


PRINTABLE = frozenset(string.printable)

# ### LIGHTWEIGHT ASSERTIONS FOR RE-USE ### #


def _msg_if(msg):
    return "" if msg is None else f": {msg}"


def _assert_in(status, msgs, msg=None, enforce=True):
    ok = status in msgs
    result = None
    if not ok:
        result = f"{status} should be in {msgs}" + _msg_if(msg)
        if enforce:
            assert status in msgs, result

    return ok, result


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


class DryRunHelper:
    """Utility functions for dryrun"""

    @classmethod
    def singleton_logicsig_request(
        cls, program: str, args: List[ArgType], txn_params: Dict[str, Any]
    ):
        return cls.dryrun_request(program, models.LSig(args=args), txn_params)

    @classmethod
    def singleton_app_request(
        cls,
        program: str,
        args: List[ArgType],
        txn_params: Dict[str, Any],
        accounts: List[DryRunAccountType] = [],
    ):
        creator = txn_params.get("sender")
        app_idx = txn_params.get("index")
        on_complete = txn_params.get("on_complete")
        app = models.App.factory(
            creator=creator,
            app_idx=app_idx,
            on_complete=on_complete,
            args=args,
            accounts=accounts,
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
                    trace = copy(txn_res["app-call-trace"])
                    # TODO: going forward, probly only need to check the below, not the above
                    if (key := "app-call-messages") in txn_res:
                        trace += txn_res[key]
                except KeyError:
                    try:
                        ptype = "logic"
                        trace = copy(txn_res["logic-sig-trace"])
                        # TODO: further vetting reguired:
                        if (key := "logic-sig-messages") in txn_res:
                            trace += txn_res[key]
                    except KeyError:
                        continue

                for tr_idx, item in enumerate(trace):
                    if "error" in item:
                        if isinstance(item, dict):
                            error = f"{ptype} {idx} failed at line {item['line']}: {item['error']}"
                        else:
                            assert isinstance(
                                item, str
                            ), f"unexpected type {type(item)} - DryRun seems to be a moving target!!!! 06Feb2023"
                            err_msg: str = item
                            while isinstance(item, str) and tr_idx > 0:
                                tr_idx -= 1
                                item = trace[tr_idx]

                            assert isinstance(
                                item, dict
                            ), f"unexpected type {type(item)} at {tr_idx=} when back-tracking- DryRun seems to be a moving target!!!! 06Feb2023"

                            error = f"{ptype} {idx} failed at line {item['line']}: {err_msg}"
                        return error
