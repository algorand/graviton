from . import models
from .dryrun import (
    assert_error,
    assert_global_state_contains,
    assert_local_state_contains,
    assert_no_error,
    assert_pass,
    assert_reject,
    assert_status,
    make_deprecated_dryrun,
)


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
        sender=models.ZERO_ADDRESS,
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
        txns_res = make_deprecated_dryrun(self.algo_client).checked_dryrun(
            prog_drr_txns, lsig, app, sender
        )
        assert_pass(txn_index, msg, txns_res)

    def assertReject(
        self,
        prog_drr_txns,
        lsig=None,
        app=None,
        sender=models.ZERO_ADDRESS,
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
        txns_res = make_deprecated_dryrun(self.algo_client).checked_dryrun(
            prog_drr_txns, lsig, app, sender
        )
        assert_reject(txn_index, msg, txns_res)

    def assertStatus(
        self,
        prog_drr_txns,
        status,
        lsig=None,
        app=None,
        sender=models.ZERO_ADDRESS,
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
        txns_res = make_deprecated_dryrun(self.algo_client).checked_dryrun(
            prog_drr_txns, lsig, app, sender
        )
        assert_status(status, txn_index, msg, txns_res)

    def assertNoError(
        self,
        prog_drr_txns,
        lsig=None,
        app=None,
        sender=models.ZERO_ADDRESS,
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
        # drr = self.mixin_dryrun_request(prog_drr_txns, lsig, app, sender)
        drr = make_deprecated_dryrun(self.algo_client).deprecated_dryrun(
            prog_drr_txns, lsig, app, sender
        )
        assert_no_error(drr, txn_index=txn_index, msg=msg)

    def assertError(
        self,
        prog_drr_txns,
        contains=None,
        lsig=None,
        app=None,
        sender=models.ZERO_ADDRESS,
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

        # drr = self.mixin_dryrun_request(prog_drr_txns, lsig, app, sender)
        drr = make_deprecated_dryrun(self.algo_client).deprecated_dryrun(
            prog_drr_txns, lsig, app, sender
        )

        assert_error(drr, contains=contains, txn_index=txn_index, msg=msg)

    def assertGlobalStateContains(
        self,
        prog_drr_txns,
        delta_value,
        app=None,
        sender=models.ZERO_ADDRESS,
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

        txns_res = make_deprecated_dryrun(self.algo_client).checked_dryrun(
            prog_drr_txns, lsig=None, app=app, sender=sender
        )
        assert_global_state_contains(delta_value, txn_index, txns_res, msg=msg)

    def assertLocalStateContains(
        self,
        prog_drr_txns,
        addr,
        delta_value,
        app=None,
        sender=models.ZERO_ADDRESS,
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

        txns_res = make_deprecated_dryrun(self.algo_client).checked_dryrun(
            prog_drr_txns, lsig=None, app=app, sender=sender
        )
        assert_local_state_contains(addr, delta_value, txn_index, txns_res, msg=msg)

    @staticmethod
    def default_address():
        """Helper function returning default zero addr"""
        return models.ZERO_ADDRESS
