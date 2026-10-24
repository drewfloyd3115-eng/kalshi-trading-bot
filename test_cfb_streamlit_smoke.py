"""Optional UI smoke test, activated where streamlit is installed."""
import importlib.util
import unittest

@unittest.skipUnless(importlib.util.find_spec('streamlit') is not None, 'streamlit not available in this offline runner')
class CFBStreamlitSmoke(unittest.TestCase):
    def test_empty_ui_is_fail_closed(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file('cfb_model_app.py',default_timeout=20).run()
        self.assertFalse(at.exception,str(at.exception))
        self.assertTrue(any('No games loaded' in str(x.value) for x in at.info))
