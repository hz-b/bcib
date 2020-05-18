import logging
# logging.basicConfig(level='DEBUG')
from bcib.threaded_bridge import setup_threaded_callback_iterator_bridge
import threading
import unittest
import functools

logger = logging.getLogger('bcib')


class TestExecutor(unittest.TestCase):
    def setUp(self):
        self.bridge = setup_threaded_callback_iterator_bridge()

    def _run_in_execute(self, partial):
        raise NotImplementedError

        def do_exec():
            self.bridge.execute()

        self.thread = threading.Thread(target=do_exec)
        self.thread.start()
        r = self.bridge.submit(partial)
        self.bridge.stopDelegation()
        self.thread.join()
        return r

    def _run_as_iterator(self, partials):

        # Make sure partials are iterables
        l = len(partials)

        def do_iter():
            for elem in self.bridge:
                logger.debug(f'Got element {elem}')
            logger.info('Finished iteration')

        self.thread = threading.Thread(target=do_iter)
        self.thread.start()
        try:
            for p in partials:
                r = self.bridge.submit(p)
                logger.debug(f'Submission {p} produced result {r}')
        except Exception as exc:
            logger.error(f'Executor submission raised exc {exc}')
            raise exc
        finally:
            logger.debug('Stopping command execution')
            self.bridge.stopDelegation()
        logger.info('Waiting for threads to join')
        self.thread.join()
        return r

    def test00_iter_stop(self):
        '''Simple startup close test
        '''
        def cmd():
            yield None
            return

        partial = functools.partial(cmd)
        self._run_as_iterator([partial])
        logger.info('done')

    def no00_execute_stop(self):
        '''Simple startup close test
        '''
        def cmd():
            # Just a no op
            return

        partial = functools.partial(cmd)
        self._run_in_execute(partial)
        logger.info('done')

    def test00_simple_command(self):
        '''Send a simple command
        '''
        def cmd():
            logger.info('Executing test command')
            yield 'Test'
            return 'Result'

        partial = functools.partial(cmd)
        r = self._run_as_iterator([partial])
        self.assertEqual(r, 'Result')
        logger.info('done')

    def test01_more_yields(self):
        '''Send two commands
        '''
        def cmd():
            logger.info('Executing test command')
            yield 'Test'
            yield 'Test1'
            return 'Result 2'

        partial = functools.partial(cmd)
        r = self._run_as_iterator([partial])
        self.assertEqual(r, 'Result 2')
        logger.info('done')

    def test02_two_commands(self):
        '''Sending two commands
        '''
        def cmd():
            logger.info('Executing test command 1')
            yield 'Test'
            return 'Result 1'

        def cmd2():
            logger.info('Executing test command2')
            yield 'Test2'
            return 'Result 2'

        p1 = functools.partial(cmd)
        p2 = functools.partial(cmd2)
        r = self._run_as_iterator([p1, p2])
        self.assertEqual(r, 'Result 2')
        logger.info('done')

    def test03_execute_two_times(self):
        '''Sending one command after the other
        '''
        def cmd():
            logger.info('Executing test command')
            yield 'Test'
            return 'Result 1'

        def cmd2():
            logger.info('Executing test command')
            yield 'Test2'
            return 'Result 2'

        p1 = functools.partial(cmd)
        p2 = functools.partial(cmd2)
        r = self._run_as_iterator([p2])
        r = self._run_as_iterator([p1])
        self.assertEqual(r, 'Result 1')
        logger.info('done')

    def test04_execute_many_times_many_commands(self):
        '''Sending one command after the other
        '''
        def cmd():
            logger.info('Executing test command')
            yield 'Test'
            return 'Result 1'

        def cmd2():
            logger.info('Executing test command2')
            yield 'Test2'
            return 'Result 2'

        def cmd3():
            logger.info('Executing test command3')
            yield 'Test3'
            return 'Result 3'

        p1 = functools.partial(cmd)
        p2 = functools.partial(cmd2)
        p3 = functools.partial(cmd3)
        r = self._run_as_iterator([p1])
        self.assertEqual(r, 'Result 1')
        r = self._run_as_iterator([p2])
        self.assertEqual(r, 'Result 2')
        r = self._run_as_iterator([p3])
        self.assertEqual(r, 'Result 3')
        r = self._run_as_iterator([p2, p3, p1])
        self.assertEqual(r, 'Result 1')
        r = self._run_as_iterator([p1, p3, p2])
        self.assertEqual(r, 'Result 2')
        r = self._run_as_iterator([p1, p2, p3])
        self.assertEqual(r, 'Result 3')
        logger.info('done')


if __name__ == '__main__':
    unittest.main()
