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
    3. the return value of the executed object is returned back
       to the callback
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
            # Use the element
            # Author's use case: a message that's yielded to
            # bluesky's run engine
            pass

    thread = threading.Thread(target=iterate)
    thread.start()
    try:
        # The partials would be a list of user commands.
        # Typically the method
        for p in partials:
            r = bridge.submit(p)
    finally:
        bridge.stopDelegation()
        .thread.join()


please use *only* instances of
:class:`bcib.CallbackIteratorBridge` directly
'''
from .bridge import CallbackIteratorBridge
from .exceptions import ExecutionStopRequest
