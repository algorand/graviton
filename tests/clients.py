from algosdk.v2client.algod import AlgodClient

# from algosdk.kmd import KMDClient
# from algosdk.v2client.indexer import IndexerClient

DEVNET_TOKEN = "a" * 64
ALGOD_PORT = 4001
# KMD_PORT = 4002
# INDEXER_PORT = 8980


def get_algod() -> AlgodClient:
    return AlgodClient(DEVNET_TOKEN, f"http://localhost:{ALGOD_PORT}")


# def get_kmd() -> KMDClient:
#     return KMDClient(DEVNET_TOKEN, f"http://localhost:{KMD_PORT}")


# def get_indexer() -> IndexerClient:
#     return IndexerClient(DEVNET_TOKEN, f"http://localhost:{INDEXER_PORT}")
