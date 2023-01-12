import pytest

from graviton.inspector import DryRunInspector


def test_from_single_response_errors():
    error_resp = {
        "error": "dryrun Source[0]: 1 error",
        "protocol-version": "future",
        "txns": None,
    }

    with pytest.raises(AssertionError) as ae:
        DryRunInspector.from_single_response(error_resp, None, None)

    assert (
        ae.value.args[0]
        == "dryrun response included the following error: [dryrun Source[0]: 1 error]"
    )

    no_txns_resp1 = {
        "error": None,
        "protocol-version": "future",
        "txns": None,
    }

    with pytest.raises(AssertionError) as ae:
        DryRunInspector.from_single_response(no_txns_resp1, None, None)

    assert (
        ae.value.args[0]
        == "require exactly 1 dry run transaction to create a singleton but had 0 instead"
    )

    no_txns_resp2 = {
        "protocol-version": "future",
        "txns": None,
    }

    with pytest.raises(AssertionError) as ae:
        DryRunInspector.from_single_response(no_txns_resp2, None, None)

    assert (
        ae.value.args[0]
        == "require exactly 1 dry run transaction to create a singleton but had 0 instead"
    )

    too_many_txns_resp = {"protocol-version": "future", "txns": [1, 2, 3]}

    with pytest.raises(AssertionError) as ae:
        DryRunInspector.from_single_response(too_many_txns_resp, None, None)

    assert (
        ae.value.args[0]
        == "require exactly 1 dry run transaction to create a singleton but had 3 instead"
    )

    too_many_txns_resp_w_err = {
        "error": "this is REALLLY REALLY BAD!!!",
        "protocol-version": "future",
        "txns": [1, 2, 3],
    }

    with pytest.raises(AssertionError) as ae:
        DryRunInspector.from_single_response(too_many_txns_resp_w_err, None, None)

    assert (
        ae.value.args[0]
        == "dryrun response included the following error: [this is REALLLY REALLY BAD!!!]"
    )
