import logging
import traceback


class SafeFormatter(logging.Formatter):
    """Keep traceback locations without exception strings, SQL, or credential values."""

    def formatException(self, exc_info):
        return "".join(traceback.format_tb(exc_info[2])) + exc_info[0].__name__


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeFormatter("%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
