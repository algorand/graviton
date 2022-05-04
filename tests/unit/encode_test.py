import pytest

from graviton.blackbox import DryRunEncoder


def test_encode_arg():
    encoder = DryRunEncoder._encode_arg

    idx = 17

    expected = arg = b"I am bytes I am"
    assert expected == encoder(arg, idx)

    expected = arg = "I am a string I am"
    assert expected == encoder(arg, idx)

    arg = 42
    expected = arg.to_bytes(8, "big")
    assert expected == encoder(arg, idx)

    arg = 42.1337
    with pytest.raises(AssertionError) as ae:
        encoder(arg, idx)

    assert (
        ae.value.args[0]
        == "problem encoding arg (42.1337) at index (17): can't handle arg [42.1337] of type <class 'float'>"
    )
