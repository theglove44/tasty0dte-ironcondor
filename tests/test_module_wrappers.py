import unittest


class TestModuleWrappers(unittest.TestCase):
    def test_core_root_modules_alias_packaged_implementations(self):
        import jade_lizard
        import logger
        import main
        import monitor
        import premium_popper
        import strategy

        self.assertEqual(main.__name__, "tasty0dte.main")
        self.assertEqual(strategy.__name__, "tasty0dte.strategy")
        self.assertEqual(monitor.__name__, "tasty0dte.monitor")
        self.assertEqual(logger.__name__, "tasty0dte.logger")
        self.assertEqual(premium_popper.__name__, "tasty0dte.premium_popper")
        self.assertEqual(jade_lizard.__name__, "tasty0dte.jade_lizard")

