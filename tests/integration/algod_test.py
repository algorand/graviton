from tests.clients import get_algod


def test_algod():
    algod = get_algod()
    url = algod.algod_address
    print(f"algod.url: {url}")
    status = algod.status()
    print(f"algod.status(): {status}")
    assert status, "somehow got nothing out of Algod's status"
