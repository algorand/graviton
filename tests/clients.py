from algosdk.v2client.algod import AlgodClient

DEVNET_TOKEN = "a" * 64
ALGOD_PORT = 4001


def get_algod() -> AlgodClient:
    return AlgodClient(DEVNET_TOKEN, f"http://localhost:{ALGOD_PORT}")
