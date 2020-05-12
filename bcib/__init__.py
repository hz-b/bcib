'''Bridge callback to iterator

Many solvers typically expect to call functions and receive
values. Bluesky's run engine e.g. expects to consume messages
provided by an iterator.

This module provides a bridge. The bridge can be called via
:meth:`submit`. It uses queues to deliver callable objects to the
consumer of the iterator. The object is expected to yield values.
Values returned by the executed object will then be passed back
and returned to the callback.

A state engine is used to supervise the state that:
    1. an object is received
    2. the object is executed and the yielded  messages handed to
      the consuming object
    3. the return value of the exeucted object is returned back
       to the calllback
    4. a new command is only accepted after the steps above have
       been completed

Please note:
    The iterator and the callback have to run in different
    concurrently executed entities (e.g. threads).

Common use case would be:
::
    from bcib.threaded_bridge import setup_threaded_callback_iterator_bridge

    bridge = setup_threaded_callback_iterator_bridge()

    def iterate():
        for elem in self.bridge:
            pass

    thread = threading.Thread(target=iterate)
    self.thread.start()
    try:
        for p in partials:
            r = self.bridge.submit(p)
    finally:
        self.bridge.stopDelegation()
        self.thread.join()

    please use *only* instances of
    :class:`CallbackIteratorBridge` directly
'''
from .bridge import CallbackIteratorBridge
from .exceptions import ExecutionStopRequest