from bluesky import plan_stubs as bps, preprocessors as bpp
import logging

logger = logging.getLogger('bcib')

def bridge_plan_stub(bridge, log=None):

    if log is None:
        log = logger

    stop_method = bridge.stopDelegation
    def run_inner(bridge):
        return (yield from bridge)

    try:
        r = (yield from run_inner(bridge))
    except Exception as exc:
        logger.error(f'bridge_plan_stub: Failed to execute {bridge} reason: {exc}')
        raise exc
    finally:
        logger.info(f'bridge_plan_stub: End of evaluating {bridge}')
        stop_method()

    return r