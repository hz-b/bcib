from .bridge import CallbackIteratorBridge
from queue import Queue


def setup_threaded_callback_iterator_bridge():
    '''Convenience function for setting up the callback bridge
    '''
    q_cmd = Queue(maxsize=1)
    q_res = Queue(maxsize=1)

    executor = CallbackIteratorBridge(command_queue=q_cmd, result_queue=q_res)
    return executor
