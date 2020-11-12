'''Interface definition of the callback to iterator bridge

Many solvers typically expect to call functions and receive
values. Bluesky's run engine e.g. expects to consume messages
provided by an iterator.


Interfaces:

 * the interface of the bridge itself
   :class:`CallbackIteratorBridgeInterface`.

'''

from abc import ABCMeta, abstractmethod


class CallbackIteratorBridgeInterface(metaclass=ABCMeta):
    '''Delegate submitted plans to the iterator consumer

    Args:
        command_queue :    a queue of length 1
        result_queue  :    a queue of length 1
        next_cmd_timeout : maximum time to wait for the next command
        cmd_exec_timeout : maximum time to wait for the return value
                           of the executed command
        log :              a logger.Logger instance. If not given a
                           default logger will be used

    User is expected to submit command using :meth:`submit`.
    These command will then appear to the iterator consumer.
    This executor can be used by functions that expect a callback.
    The callback is then responsible to submit its commands using
    :meth:`submit`. These callbacks are then handed out from the
    __iter__ method.

    This approach allows:
        * passing a plan to the run engine
        * execute the call back in a separate coroutine thread
          or callback

    Warning:
        * The user of the method submit must be run in a different
          thread than the consumer of the generator.

        * Implementation can require that the queues are exactly of
          length one

        * Timeout values should be carefully selected.

    Todo:
        * Consider making the bridge a context manager.

          * When entering the bridge would be reset. (e.g.
            queues cleared)
          * When finishing stopDelegation would be issued.

        * Check naming: Brige pattern as interface definition separate
          from implementation. Delegator as a callback delegates to the
          consumer of the iterator.

    If you are using it in a threaded environment function
    :func:`bcib.threaded_bridge.setup_threaded_callback_iterator_bridge`
    can be used to setup such a bridge.

    Typical usage:

    ::

        bridge = setup_bridge()
        def cb(x):
            r = bridge.submit(x)
            return r

        sv_x = solver(x0, cb)
        bridge.stopDelegation()

    '''

    @abstractmethod
    def __init__(self, *, command_queue, result_queue,
                 next_cmd_timeout, cmd_exec_timeout, log=None):
        raise NotImplementedError('Implement in derived class')

    @abstractmethod
    def submit(self, obj, wait_for_result=True):
        '''Submit a command to the iterator

        In a typical callback the user will submit an object. This
        object will then be yielded by the iterator.

        Args:
            obj:              object to hand over to the delegator
                              user
            wait_for_result : if the end result shall be waited for.
                              Typically only used internally.
                              Set to false when stopping delegation
        Returns:
            the value returned by the iteration
        '''
        raise NotImplementedError('Implement in derived class')

    @abstractmethod
    def __iter__(self):
        '''
        '''
        raise NotImplementedError('Implement in derived class')

    @abstractmethod
    def stopDelegation(self, fail_mode=False):
        raise NotImplementedError('Implement in derived class')
