'''Integrating a solver with bluesky

This example rather shows that the current interface still
requires improvement.
'''
import logging
from bcib.threaded_bridge import setup_bridge
from bcib.bridge_plan import bridge_plan_stub
from ophyd import Component as Cpt, Device, Signal
from ophyd.status import AndStatus

from bluesky import RunEngine
from bluesky.callbacks import LiveTable

import bluesky.plans as bp
import bluesky.plan_stubs as bps

from scipy.optimize import brentq
import threading
from functools import partial
import enum


class MimicActuator(Device):
    setpoint = Cpt(Signal, name='setp', value=0.0)
    readback = Cpt(Signal, name='rbk', value=0.0)

    def set(self, val):
        stat_set = self.setpoint.set(val)
        # A real strange but predictable device
        f = val**3 * 2 + 10
        stat_rbk = self.readback.set(f)
        return AndStatus(stat_set, stat_rbk)


class SolverState(enum.IntEnum):
    failed = -1
    unknown = 0
    searching = 1
    finished = 2


class Bookkeeping(Device):
    target = Cpt(Signal, name='tgt', value=0.0)
    status = Cpt(Signal, name='tgt', value=0.0)

    def stop(self, success=False):
        if success:
            self.status.set(SolverState.finished)
        else:
            self.status.set(SolverState.failed)


def solve_stub(detectors, motor, step, log=None):
    '''

    This stub should be a bit more generic
    '''
    bk_dev = detectors[0]

    yield from bps.checkpoint()
    yield from bps.mv(bk_dev.status, SolverState.unknown)

    def step_stub(detectors, motor, x):
        yield from bps.checkpoint()
        yield from bps.mv(motor, x)
        all_dev = list(detectors) + [motor]
        r = (yield from bps.trigger_and_read(all_dev))
        return r

    def cb(val):
        cmd = partial(step_stub, detectors, motor, val)
        r = bridge.submit(cmd)
        val = r[motor.readback.name]['value']
        return val - step

    bridge = setup_bridge()

    def run_solver():
        a, b = -10, 10
        r = brentq(cb, a, b)
        bridge.stopDelegation()
        return r

    yield from bps.mv(bk_dev.status, SolverState.searching)
    yield from bps.mv(bk_dev.target, step)

    thread = threading.Thread(target=run_solver, name='run_solver')
    thread.start()

    try:
        (yield from bridge_plan_stub(bridge, log=log))
    except Exception:
        yield from bps.mv(bk_dev.status, SolverState.failed)
    else:
        yield from bps.mv(bk_dev.status, SolverState.finished)

    thread.join()
    del thread


def main():
    act = MimicActuator(name='act')
    bk_dev = Bookkeeping(name='bk')
    dets = [bk_dev]
    RE = RunEngine({})
    RE.log.setLevel(logging.DEBUG)

    lt = LiveTable([bk_dev.status.name, bk_dev.target.name,
                    act.setpoint.name, act.readback.name])
    RE(bp.scan(dets, act, 1, 5, 5, per_step=solve_stub), lt)


if __name__ == '__main__':
    main()
