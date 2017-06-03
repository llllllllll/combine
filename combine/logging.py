"""Logging utilities.
"""
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache, partial
import operator as op
import sys
from sys import _getframe
from types import ModuleType

from humanize import naturaldelta
from logbook import Logger, ERROR, NOTICE, DEBUG
from logbook.more import ColorizedStderrHandler

from .utils.apply import instance


class AlternateColorizedStderrHandler(ColorizedStderrHandler):
    """A logbook colorized handler that uses a different set of colors.
    """
    def get_color(self, record):
        level = record.level
        if level >= ERROR:
            return 'red'
        if level >= NOTICE:
            return 'yellow'
        if level == DEBUG:
            return 'darkteal'
        return 'lightgray'


default_format_string = (
    '[{record.time:%Y-%m-%d %H:%M:%S.%f}]'
    ' {record.level_name}: {record.channel}: {record.message}'
)


def _get_logger_for_contextmanager(log):
    """Get the canonical logger from a context manager.

    Parameters
    ----------
    log : Logger or None
        The explicit logger passed to the context manager.

    Returns
    -------
    log : Logger
        The logger to use in the context manager.
    """
    if log is not None:
        return log

    # We need to walk up through the context manager, then through
    # @contextmanager and finally into the top level calling frame.
    return _logger_for_frame(_getframe(3))


@contextmanager
def log_duration(operation, level='info', log=None):
    """Log the duration of some process.

    Parameters
    ----------
    operation : str
        What is being timed?
    level : str, optional
        The level to log the start and end messages at.
    log : Logger, optional
        The logger object to write to. By default this is the logger for the
        calling frame.
    """
    log = _get_logger_for_contextmanager(log)

    log.log(level.upper(), operation)
    start = datetime.now()
    try:
        yield
    finally:
        now = datetime.now()
        log.log(
            level.upper(),
            'completed {} (completed in {})',
            operation,
            naturaldelta(now - start),
        )


_mem_logger = lru_cache(None)(Logger)


def _logger_for_frame(f):
    """Return the memoized logger object for the given stackframe.

    Parameters
    ----------
    f : frame
        The frame to get the logger for.

    Returns
    -------
    logger : Logger
        The memoized logger object.
    """
    return _mem_logger(f.f_globals['__name__'])


@partial(op.setitem, sys.__modules__, __name__)
@instance
class logging(ModuleType):
    def __init__(self):
        super().__init__(type(self).__name__, '')
        vars(self).update(globals())

    @property
    def log(self):
        return _logger_for_frame(_getframe(1))


log = logging.log
