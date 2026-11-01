import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings

from desktop_client.settings import (
    KEYRING_SERVICE,
    KEYRING_USERNAME,
    DesktopSettings,
    SettingsStore,
)


class DesktopSettingsTests(unittest.TestCase):
    def test_api_key_is_saved_to_keyring_not_qsettings(self) -> None:
        persisted_values: dict[str, str] = {}

        class FakeQSettings:
            Status = QSettings.Status

            def __init__(self, *_: str) -> None:
                pass

            def setValue(self, key: str, value: str) -> None:
                persisted_values[key] = value

            def sync(self) -> None:
                pass

            def status(self) -> QSettings.Status:
                return QSettings.Status.NoError

        with (
            patch("desktop_client.settings.QSettings", new=FakeQSettings),
            patch("desktop_client.settings.keyring.set_password") as set_password,
        ):
            store = SettingsStore()
            store.save(
                DesktopSettings(
                    backend_mode="remote",
                    remote_api_key="private-api-key",
                )
            )

        self.assertNotIn("remote_api_key", persisted_values)
        set_password.assert_called_once_with(
            KEYRING_SERVICE,
            KEYRING_USERNAME,
            "private-api-key",
        )


if __name__ == "__main__":
    unittest.main()