"""Bitcast miner entry point: ``python -m neurons.miner``."""

import atexit

import bittensor as bt

from bitcast.config import build_config, get_settings
from bitcast.loki import init_loki, shutdown_loki_sync
from bitcast.miner.server import Miner
from bitcast.sentry import init_sentry


def main() -> None:
    config = build_config("miner")
    settings = get_settings()
    init_sentry(settings)
    bt.logging.info(f"Starting miner with config: {config}")

    miner = Miner(config)

    # Initialise Loki with miner labels (uid known after Miner init)
    from bitcast import __version__

    init_loki(
        settings,
        labels={
            "hotkey": miner.wallet.hotkey.ss58_address,
            "netuid": str(config.netuid),
            "mechid": str(settings.mechid),
            "neuron": "miner",
            "version": __version__,
        },
    )

    # Register sync shutdown for clean exit (KeyboardInterrupt, atexit)
    atexit.register(shutdown_loki_sync)

    try:
        miner.run()
    except KeyboardInterrupt:
        bt.logging.info("Miner interrupted.")
    finally:
        shutdown_loki_sync()


if __name__ == "__main__":
    main()
