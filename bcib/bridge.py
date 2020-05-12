'''Bridge callback to iterator

Many solvers typically expect to call functions and receive
values. Bluesky's run engine e.g. expects to consume messages
provided by an iterator.



Warning:
    please use currently *only* instance of
    :class:`CallbackIteratorBridge`.

Currently only instances of :class:`CallbackIteratorBridge` should
be used. It has only be tested in a threading environement, as the
queues and the state_machines are shared the brige and delegator.

Separate instances of :class:`_BridgeToDelegator` and
:class:`_DelegateToIterator` could be used. This would required
:however: that the state_machines would be shared too.
'''

import itertools
import queue
import traceback
import sys
import logging
import enum
import super_state_machine.machines

logger = logging.getLogger('bcib')


class ExecutionStopRequest(RuntimeError):
    pass


class CommandProcessingState(super_state_machine.machines.StateMachine):
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
        transitions =  {
            'undefined'  : ['submitting', 'failed'],
            'submitting' : ['submitted', 'failed'],
            'submitted'  : ['waiting', 'finished', 'failed'],
            'waiting'    : ['finished', 'failed'],
            'finished'   : ['submitting', 'failed'],
            #'failed'     : ['submitting'],
        }

class ExecutorState(super_state_machine.machines.StateMachine):
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
        transitions =  {
            'undefined'  : ['running', 'stopping', 'failed'],
            'running' : ['stopping', 'failed'],
            'stopping' : ['stopped', 'failed'],
            'stopped' : ['running', 'failed']
        }


class EndOfEvaluation:
    '''Evaluation ended
    '''

end_of_evaluation = EndOfEvaluation()

class _BaseClass_Bridge_Delegator:
    '''Base class

    Both classes :class:`_BridgeToDelegator` and
    :class:`_DelegateToIterator`need the member defined below.
    These classes do not inherit directly from this class, as
    :class:`CallbackIteratorBridge` inherits from both these classes.
    '''
    def __init__(self, *, command_queue, result_queue, log=None,
                maxtime_for_next_command=5, command_execution_timeout=5):

        self.state = ExecutorState()
        self.cmd_state = CommandProcessingState()

        self.command_queue = command_queue
        self.result_queue = result_queue

        if log is None:
            log = logger
        self.log = log

        # Shall these timeouts be kept in a book keeping device
        self.maxtime_for_next_command = maxtime_for_next_command
        self.command_execution_timeout = command_execution_timeout

        self.last_command = None

    def __repr__(self):
        cls_name = self.__class__.__name__
        txt = (
            f'{cls_name}('
            f' command_queue={self.command_queue},'
            f' result_queue={self.result_queue},'
            f' command_queue_timeout={self.maxtime_for_next_command},'
            f' command_execution_timeout={self.command_execution_timeout},'
            ' )'
        )
        return txt

    #-------------------------------------------------------------------------
    def clearQueues(self):
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



class _BridgeToDelegator:
    '''Delegate values received by callbacks to the iterator

    Warning:
        This 
    '''

    def stopDelegation(self, fail_mode=False):
        cls_name = self.__class__.__name__
        if self.state.is_stopped:
            txt = 'command delegation stopped. Not stopping again'
            self.log.info(f'{cls_name}: {txt}')
            return
        
        if self.state.is_stopping:
            txt = 'command delegation already asked to stop. Not trying to stop it again'
            self.log.info(f'{cls_name}: {txt}')
            return
        
        if self.cmd_state.is_waiting:
            txt = f'{cls_name}: still waiting for  response to delegated command {self.last_command}'
            self.log.info(txt)

        if not self.state.is_failed:
            self.state.set_stopping()

        self.log.info(f'{cls_name}: stopping command execution')

        if fail_mode:
            # Be sure to empty queues
            self.clearQueues()
        # Inform bluesky that we are done ...
        self.submit(end_of_evaluation, wait_for_result=False)
        self.state.set_stopped()
        self.log.info(f'{cls_name}: command execution stopped')

    def submit(self, cmd, wait_for_result=True):

        #if self.state.is_stopped:
        #    self.clearQueues()
        #    self.state.set_running()

        command_queue_put_timeout = 10
        self.cmd_state.set_submitting()
        self.last_command = cmd
        self.command_queue.put(cmd, timeout=command_queue_put_timeout)
        self.cmd_state.set_submitted()
        if not wait_for_result:
            self.cmd_state.set_finished()
            return 
        
        self.cmd_state.set_waiting()
        try:
            r = self.result_queue.get(timeout=self.command_execution_timeout)
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


class _DelegateToIterator(_BaseClass_Bridge_Delegator):
    def __iter__(self):
        '''Return appropriate bluesky plans

        Heavy lifting done by :meth:`_iterInner`
        '''
        # self.checkOnStart()

        r = None
        try:
            r = (yield from self.execute(as_iter=True))
        finally:
            self.log.info(f'Iterator finished. Returning value {r}')
            return r

    def execute(self, as_iter=False):

        if self.state.is_stopped:
            txt = 'Executor in stopped state. Setting it back to running'
            self.log.info(txt)
            self.state.set_running()
            #raise AssertionError(txt)

        if self.state.is_stopping:
            logger.waring('Executor is stopping. Still asked to restart')
        
        cls_name = self.__class__.__name__
        self.log.info(f'{cls_name}: waiting for commands to execute')

        for cnt in itertools.count():
            cmd = self.command_queue.get(self.maxtime_for_next_command)

            if cmd is end_of_evaluation:
                # That's all folks
                self.log.info(f'{cls_name}: evaluation finished')
                return

            self.log.info(f'{cls_name}: executing cmd no. {cnt}: {cmd}')

            try:
                if as_iter:
                    # Consider yielding command per command
                    r = (yield from self._executeSingle(cmd, as_iter=as_iter) )
                else:
                    r = self._executeSingle(cmd, as_iter=as_iter)
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

    def _executeSingle(self, cmd, as_iter=False):
        '''
        Todo
            Consider if a 'static' or instance message is yielded
            as soons execution stops.

            Why:
                e.g. bluesky deferred pause request. Inform bluesky
                     that user should interact...
        '''

        if not as_iter:
           raise NotImplementedError('Direct call is not tested yet')

        cls_name = self.__class__.__name__
        self.log.info(f'{cls_name}: waiting for commands to execute')

        fmt = (
                '{}: status is {} but commands are still requested to be executed.'
                'Stopping before executing cmd {}'
        )

        def run_iter(a_iter):
            '''A much ado about intercepting in between all these messages

            Todo:
                This code does not work together with bluesky
            '''
            while True:
                try:
                    c = next(a_iter)
                except StopIteration as si:
                    return si.value

                if self.state.is_stopping:
                    txt = (
                        f'{cls_name} Request for stopping command execution.'
                        f' Stopping before executing cmd {c}'
                    )
                    self.log.info(txt)
                    raise ExecutionStopRequest(txt)
                elif self.state.is_stopped:
                    txt = fmt.format(cls_name, self.state.state, c)
                    self.log.warning(txt)
                    raise ExecutionStopRequest(txt)
                elif self.state.is_failed:
                    txt = fmt.format(cls_name, self.state.state, c)
                    self.log.warning(txt)
                    raise ExecutionStopRequest(txt)

                yield c

        if as_iter:
            r = (yield from cmd() )
            # r = (yield from run_iter(cmd()) )
        else:
            raise NotImplementedError('Not tested yet')
            r = cmd()
        return r

class CallbackIteratorBridge(_BridgeToDelegator, _DelegateToIterator,
                             _BaseClass_Bridge_Delegator):
    '''Delegate submitted plans to the iterator consumer
    
    Follows delegator pattern.

    Args:
        log :           a logger.Logger instance. Typically the
                        logger of the RunEngine
        command_queue : a queue of length 1
        result_queue  : a queue of length 1

    User is expected to submit command using method :submit:. 
    These command will then appear to the iterator consumer.
    This executor can be used by functions that expect a collback.
    The callback is then responsible to submit its commands using
    :meth: submit. These callbacks are then handed out from the 
    __iter__ method. 

    This approach allows:
        * passing a plan to the run engine 
        * execute the call back in a separate coroutine thread
          or callback

    Warning:
        The callback and the run engine must not be executed in
        different runnable entities (e.g. different threads)
        The queues must match these settings.

    '''
