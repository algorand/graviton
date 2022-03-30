from algosdk.v2client.algod import AlgodClient

# from algosdk.kmd import KMDClient
# from algosdk.v2client.indexer import IndexerClient

DEVNET_TOKEN = "a" * 64
ALGOD_PORT = 4001


def get_algod() -> AlgodClient:
    return AlgodClient(DEVNET_TOKEN, f"http://localhost:{ALGOD_PORT}")
