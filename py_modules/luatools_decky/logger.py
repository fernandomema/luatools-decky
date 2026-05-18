from __future__ import annotations

import sys

try:
    import decky
    _DECKY_AVAILABLE = True
except Exception:
    _DECKY_AVAILABLE = False


class _DeckyLogger:
    def log(self, message: str) -> None:
        if _DECKY_AVAILABLE:
            decky.logger.info(message)
        else:
            print(message)

    def warn(self, message: str) -> None:
        if _DECKY_AVAILABLE:
            decky.logger.warning(message)
        else:
            print(message, file=sys.stderr)

    def error(self, message: str) -> None:
        if _DECKY_AVAILABLE:
            decky.logger.error(message)
        else:
            print(message, file=sys.stderr)

    def info(self, message: str) -> None:
        self.log(message)

    def debug(self, message: str) -> None:
        if _DECKY_AVAILABLE:
            decky.logger.debug(message)
        else:
            self.log(message)


logger = _DeckyLogger()
