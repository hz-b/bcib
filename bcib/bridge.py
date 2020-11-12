'''Bridge callback to iterator

Many solvers typically expect to call functions and receive
values. Bluesky's run engine e.g. expects to consume messages
provided by an iterator.

The implementation of the bridge is split up in 4 parts.
    1. the base class. Defines a common __init__ and setup of state
    2. a mixin class defining the submit method
    3. a mixin class defining the __iter__ method
    4. a class inherting from 2 and 3 that makes then the full bridge

Motivation: the submit and __iter__ could be used in different
processe or decoupled object.

Warning:
    Currently only instances of :class:`CallbackIteratorBridge`
    should be used. It has only be tested in a threading
    environment, as the queues and the state_machines are shared
    by the bridge and delegator.

Todo:
    * consider to drop the extra complexity
    * consider how to handle RunEngine.stop and thus RunEngine.resume
'''

from .exceptions import ExecutionStopRequest
from super_state_machine.machines import StateMachine

import itertools
import queue
import traceback
import sys
import logging
import enum
from .bridge_interface import CallbackIteratorBridgeInterface

logger = logging.getLogger('bcib')


class CommandProcessingState(StateMachine):
    '''treat commands in a single file fashion

    This state machine is used to trace that the only
    "one one passenger is using the bridge at a time"

    It could be seen as debugging functionality.
    '''

    class States(enum.Enum):
        UNDEFINED = 'undefined'
        # Submitted command
        SUBMITTING = 'submitting'
        SUBMITTED = 'submitted'
        # Waiting for response
        WAITING = 'waiting'
        # finished processing response
        FINISHED = 'finished'
        FAILED = 'failed'

    class Meta:
        initial_state = 'undefined'
        transitions = {
            'undefined':  ['submitting', 'failed'],
            'submitting': ['submitted', 'failed'],
            'submitted':  ['waiting', 'finished', 'failed'],
            'waiting':    ['finished', 'failed'],
            'finished':   ['submitting', 'failed'],
            'failed':     ['undefined'],
        }


class BridgeState(StateMachine):
    '''Is the bridge useable?
    '''
    class States(enum.Enum):
        UNDEFINED = 'undefined'
        RUNNING = 'running'
        # stopping: sending command out to stop
        STOPPING = 'stopping'
        # stopped. signal sent out
        STOPPED = 'stopped'
        FAILED = 'failed'

    class Meta:
        initial_state = 'undefined'
        transitions = {
            'undefined': ['running', 'stopping', 'failed'],
            'running':   ['stopping', 'failed'],
            'stopping':  ['stopped', 'failed'],
            'stopped':   ['running', 'failed']
        }


class EndOfEvaluation:
    '''Evaluation ended

    Used to inform the iterator that no further objects will be
    received.
    '''


end_of_evaluation = EndOfEvaluation()

# CallbackIteratorBridgeInterface
class _BaseClass_Bridge:
    '''Base class

    Both classes :class:`_BridgeToDelegator` and
    :class:`_DelegateToIterator` need the members defined below.
    These classes do not inherit directly from this class, as
    :class:`CallbackIteratorBridge` inherits from both these classes.

    Todo:
        * At start up it can take a bit of time until the command
          queue can be used the first time. Any subsequent use
          should be rather fast. Shoud one send a startup object
          on start?
    '''
    def __init__(self, *, command_queue, result_queue,
                 next_cmd_timeout=5, cmd_exec_timeout=5,
                 cmd_queue_timeout=1,
                 log=None):

        self.state = BridgeState()
        self.cmd_state = CommandProcessingState()

        self.command_queue = command_queue
        self.result_queue = result_queue

        if log is None:
            log = logger
        self.log = log

        # Shall these timeouts be kept in a book keeping device ?
        # That would make this module dependend on ophyd
        self.next_cmd_timeout = next_cmd_timeout
        self.cmd_exec_timeout = cmd_exec_timeout
        self.cmd_queue_timeout = cmd_queue_timeout
        self.last_command = None

    def __repr__(self):
        cls_name = self.__class__.__name__
        txt = (
            f'{cls_name}('
            f' command_queue={self.command_queue},'
            f' result_queue={self.result_queue},'
            f' next_cmd_timeout={self.next_cmd_timeout},'
            f' cmd_exec_timeout={self.cmd_exec_timeout},'
            f' cmd_queue_timeout={self.cmd_queue_timeout},'
            ' )'
        )
        return txt

    # -------------------------------------------------------------------------
    def clearQueues(self):
        '''make sure that queues are empty

        10 times: you know German "Angst". Then guess what an
        "Angsteisen" is.
        '''
        for i in range(10):
            if self.command_queue.qsize() > 0:
                try:
                    self.command_queue.get(block=False)
                except queue.Empty:
                    pass
            if self.result_queue.qsize() > 0:
                try:
                    self.result_queue.get(block=False)
                except queue.Empty:
                    pass

    def reset(self):
        if self.state.is_failed:
            self.log.info('Setting from failed to undefined')
            self.state.set_undefined()
            self.clearQueues()


class _CallbackToBrigeMixin:
    '''Delegates values received by the callback to the command queue
    '''

    def stopDelegation(self, fail_mode=False):
        '''Inform delegator that we are done
        '''
        cls_name = self.__class__.__name__
        if self.state.is_stopped:
            txt = 'command delegation stopped. Not stopping again'
            self.log.info(f'{cls_name}: {txt}')
            return

        if self.state.is_stopping:
            txt = (
                'command delegation already asked to stop. Not trying to'
                ' stop it again'
                )
            self.log.info(f'{cls_name}: {txt}')
            return

        if self.cmd_state.is_waiting:
            txt = (
                f'{cls_name}: still waiting for  response to delegated'
                f' command {self.last_command}'
            )
            self.log.info(txt)

        if not self.state.is_failed:
            self.state.set_stopping()

        self.log.info(f'{cls_name}: stopping command execution')

        if fail_mode:
            # Be sure to empty queues
            self.clearQueues()

        # Inform the iterator that we are done
        self.submit(end_of_evaluation, wait_for_result=False)
        self.state.set_stopped()
        self.log.info(f'{cls_name}: command execution stopped')

    def submit(self, cmd, wait_for_result=True):
        '''
        '''

        self.cmd_state.set_submitting()
        self.last_command = cmd
        self.command_queue.put(cmd, timeout=self.cmd_queue_timeout)
        self.cmd_state.set_submitted()
        if not wait_for_result:
            self.cmd_state.set_finished()
            return

        self.cmd_state.set_waiting()
        try:
            r = self.result_queue.get(timeout=self.cmd_exec_timeout)
        except queue.Empty:
            self.log.error(f'Did not receive response for command {cmd}')
            self.cmd_state.set_failed()
            self.state.set_failed()
            raise

        if isinstance(r, Exception):
            self.log.error(f'Command exeuction raised error {r}')
            raise r
        self.cmd_state.set_finished()
        return r


class _BridgeToIteratorMixin:
    '''Receives objects from queue and passes it to the iterator
    '''
    def __iter__(self):
        '''yield the objects

        Heavy lifting done by :meth:`exectue`
        '''
        # self.checkOnStart()

        r = None
        try:
            r = (yield from self.execute())
        finally:
            self.log.info('Iterator finished. Returning value %s', (r,))
            return r

    def execute(self):
        '''execute one command after the other.

        Receives one object after the other from :any:`command_queue`.
        Hands it over to :meth:`_executeSingle`

        Todo:
           * should be the state set automatically back to running?
           * better: context manager and let that one set it back
             to running? Why: if it stopped in the middle most probably
             an exception has happend.
        '''
        if self.state.is_stopped:
            txt = 'Executor in stopped state. Setting it back to running'
            self.log.info(txt)
            self.state.set_running()
            # raise AssertionError(txt)

        if self.state.is_stopping:
            logger.waring('Executor is stopping. Still asked to restart')

        cls_name = self.__class__.__name__
        self.log.info('%s waiting for commands to execute', (cls_name,))

        for cnt in itertools.count():
            cmd = self.command_queue.get(self.next_cmd_timeout)

            if cmd is end_of_evaluation:
                # That's all folks
                self.log.info('%s: evaluation finished', cls_name)
                return

            self.log.info(f'{cls_name}: executing cmd no, {cnt}: {cmd}')

            try:

                # Consider yielding message per message
                # That would give this part a better idea what is happening.
                # e.g. timeout reset after each command received.
                # Thus timeout after the last command.
                r = (yield from self._executeSingle(cmd))

            except Exception as exc:
                stream = sys.stderr
                stream.flush()
                txt = f'Received exception {exc} while executing cmd {cmd}'
                traceback.print_exc(stream)
                stream.write('Error: ' + txt)
                stream.flush()
                self.log.error(txt)
                self.result_queue.put(exc)
                raise exc

            self.log.info(f'cmd {cmd} produced result {r}')
            # self.command_queue.task_done()
            self.result_queue.put(r)

    def _executeSingle(self, cmd):
        '''
        Todo:
            Consider if a 'static' or instance message is yielded
            as soon as execution stops.

            Why:
                e.g. bluesky deferred pause request. Then timeouts should be
                delayed until resume is issued. Halt, abort, should be handled.
        '''

        cls_name = self.__class__.__name__
        self.log.info(f'{cls_name}: waiting for commands to execute')

        fmt = (
            '{}: status is {} but commands are still requested to be executed.'
            'Stopping before executing cmd {}'
        )

        def run_iter(a_iter):
            '''A much ado about intercepting in between all these messages

            Todo:
                This code does not work together with bluesky??
            '''
            while True:
                try:
                    val = next(a_iter)
                except StopIteration as si:
                    return si.value

                if self.state.is_stopping:
                    txt = (
                        f'{cls_name} Request for stopping command execution.'
                        f' Stopping before executing cmd {val}'
                    )
                    self.log.info(txt)
                    raise ExecutionStopRequest(txt)

                elif self.state.is_stopped or self.state.is_failed:
                    txt = fmt.format(cls_name, self.state.state, val)
                    self.log.warning(txt)
                    raise ExecutionStopRequest(txt)

                else:
                    txt = 'Why am I in state {}'.format(self.state.state)
                    raise AssertionError(txt)

                yield val

        r = (yield from cmd())
        return r


class CallbackIteratorBridge(
        _BaseClass_Bridge,
        _CallbackToBrigeMixin,
        _BridgeToIteratorMixin,
        CallbackIteratorBridgeInterface,
):
    '''Delegate submitted plans to the iterator consumer

    see :class:`CallbackIteratorBridgeInterface` for details
    '''
    ## # -------------------------------------------------------------------------
    ## # Context manager methods
    ## def __enter__(self):
    ##    self.reset()
    ##
    ## def __exit__(self, exc_type, exc_value, exc_tb):
    ##     if self.exc_type is None:
    ##         fail_mode = False
    ##     else:
    ##         fail_mode = True
    ##         self.state.set_failed()
    ##
    ##     self.stopDelegation(fail_mode)
