'''A bluesky compatible bridge plan stub

See :func:`bridge_plan_stub`
'''
# from bluesky import plan_stubs as bps, preprocessors as bpp
import logging

logger = logging.getLogger('bcib')


def bridge_plan_stub(bridge, log=None):
    '''Plan stub for evaluating the messages received over the bridge

    Yields all messages received from the bridge and returns the
    last return value. This plan can be used as a plan_stubs
    within bluesky plan_stubs or plans.

    Args:
        bridge: an instance of :class:`bcib.CallbackIteratorBridge`
        log:    a :class:`logging.Logger` object

    Returns:
        the last value received after all messages were yielded
    '''

    if log is None:
        log = logger

    stop_method = bridge.stopDelegation

    def run_inner(bridge):
        return (yield from bridge)

    try:
        r = (yield from run_inner(bridge))
    except Exception as exc:
        logger.error(
            f'bridge_plan_stub: Failed to execute {bridge} reason: {exc}'
        )
        raise exc
    finally:
        logger.info(f'bridge_plan_stub: End of evaluating {bridge}')
        stop_method()

    return r
