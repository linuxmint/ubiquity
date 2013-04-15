import io
import unittest

import mock

from ubiquity import upower


class UPowerTests(unittest.TestCase):
    @mock.patch('builtins.open')
    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    def test_has_battery(self, mock_listdir, mock_exists, mock_open):
        mock_exists.return_value = True
        mock_listdir.return_value = ['one']

        magic = mock.MagicMock(spec=io.TextIOBase)
        magic.__enter__.return_value = magic
        mock_open.return_value = magic
        magic.read.return_value = 'Battery'
        self.assertTrue(upower.has_battery())
        magic.read.return_value = 'Not a battery'
        self.assertFalse(upower.has_battery())
