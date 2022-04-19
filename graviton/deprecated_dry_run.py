from algosdk.future import transaction
from algosdk.v2client.models import DryrunRequest

from . import models
from .dryrun import DryRunHelper


def make_deprecated_dryrun(algo_client):
    return DeprecatedDryRun(algo_client, DryRunHelper.dryrun_request)


class DeprecatedDryRun:
    def __init__(self, algo_client, executor_method):
        self.algo_client = algo_client
        self.executor_method = executor_method

    def checked_dryrun(
        self, prog_drr_txns, lsig=None, app=None, sender=models.ZERO_ADDRESS
    ):
        """
        Helper function to make a dryrun request and perform basic validation
        """
        # drr = self.mixin_dryrun_request(prog_drr_txns, lsig, app, sender)
        drr = self.deprecated_dryrun(prog_drr_txns, lsig, app, sender)

        if drr["error"]:
            assert False, f"error in dryrun response: {drr['error']}"

        if not drr["txns"]:
            assert False, "empty response from dryrun"

        return drr["txns"]

    def deprecated_dryrun(self, prog_drr_txns, lsig, app, sender):
        """
        Helper function to make a dryrun request
        """
        if isinstance(prog_drr_txns, dict):
            drr = prog_drr_txns
        elif isinstance(prog_drr_txns, list):
            drr = self.deprecated_txn_dryrun(prog_drr_txns, app)
        else:
            drr = self.deprecated_source_dryrun(prog_drr_txns, lsig, app, sender)
        return drr

    def deprecated_txn_dryrun(self, txns, app):
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
            if not isinstance(app, models.App) and not isinstance(app, dict):
                raise ValueError("app must be a dict or App")
            if isinstance(app, dict):
                app = models.App(**app)

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

    def deprecated_source_dryrun(
        self, program, lsig=None, app=None, sender=models.ZERO_ADDRESS
    ):
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
        drr = DeprecatedDryRun.deprecated_exec(
            self.executor_method, program, lsig, app, sender
        )
        return self.algo_client.dryrun(drr)

    @staticmethod
    def deprecated_txn_params(sender: str, is_app: bool):
        sp = transaction.SuggestedParams(int(1000), int(1), int(100), "", flat_fee=True)
        if is_app:
            return dict(sender=sender, sp=sp, index=0, on_complete=0)

        return dict(sender=sender, sp=sp, receiver=sender, amt=0)

    @staticmethod
    def deprecated_exec(
        executor_method, program, lsig=None, app=None, sender=models.ZERO_ADDRESS
    ):
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

        if app and not isinstance(app, (models.App, dict)):
            raise ValueError("app must be a dict or App")

        if lsig and not isinstance(lsig, (models.LSig, dict)):
            raise ValueError("lsig must be a dict or LSig")

        if isinstance(app, dict):
            app = models.App(**app)
        elif isinstance(lsig, dict):
            lsig = models.LSig(**lsig)
        else:  # both are None
            lsig = models.LSig()

        if not isinstance(program, (bytes, str)):
            raise TypeError("program must be bytes or str")

        run_mode = models.get_run_mode(app)
        is_app = run_mode != "lsig"
        lsig_or_app = app if is_app else lsig
        txn_params = DeprecatedDryRun.deprecated_txn_params(sender, is_app)

        if isinstance(program, str):
            return executor_method(program, lsig_or_app, txn_params)
            # return DryRunHelper.dryrun_request(program, lsig_or_app, txn_params)

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
        #     txns = [DryRunHelper._build_appcall_signed_txn(txn, app_or_lsig)]
        #     application = cls.sample_app(sender, app_or_lsig, program)
        #     apps = [application]
        #     accounts = app_or_lsig.accounts
        #     rnd = app_or_lsig.round
        # else:
        #     txns = [DryRunHelper._build_logicsig_txn(program, txn, app_or_lsig)]

        # return DryrunRequest(
        #     txns=txns,
        #     sources=sources,
        #     apps=apps,
        #     accounts=accounts,
        #     round=rnd,
        # )
