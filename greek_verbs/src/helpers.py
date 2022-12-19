import click
import logging
import re
import threading


class ExtendedLogger(logging.Logger):
    """
    Extend the logging.Logger class.
    """
    def __init__(self, name, level=logging.NOTSET) -> None:
        self._count = 0
        self._countLock = threading.Lock()
        return super(ExtendedLogger, self).__init__(name, level)

    def _build_message(self, msg: str, arrow: str=None, indent: int=0, bold: bool=False) -> str:
        """
        Apply format parameters to a raw string.
        """
        msg = re.sub(r'\s+', ' ', str(msg).strip())

        if bold:
            msg = click.style(msg, bold=True)

        arrow_str = click.style('> ', fg=arrow, bold=True) if arrow is not None else ''
        indent_str = '  ' * indent

        msg = str(msg)
        return f'{indent_str} {arrow_str}{msg}'

    def debug(self, msg: str, *args, **kwargs):
        """
        Override the logging.Logger.debug() method and support the formatting in self._build_message().
        """
        formatted_msg = self._build_message(msg, *args, **kwargs)
        return super(ExtendedLogger, self).debug(formatted_msg)

    def info(self, msg: str, *args, **kwargs):
        """
        Override the logging.Logger.info() method and support the formatting in self._build_message().
        """
        formatted_msg = self._build_message(msg, *args, **kwargs)
        return super(ExtendedLogger, self).info(formatted_msg)

    def warning(self, msg: str, *args, **kwargs):
        """
        Override the logging.Logger.warning() method and support the formatting in self._build_message().
        """
        formatted_msg = self._build_message(msg, *args, **kwargs)
        return super(ExtendedLogger, self).warning(formatted_msg)

    def error(self, msg: str, *args, **kwargs):
        """
        Override the logging.Logger.error() method and support the formatting in self._build_message().
        """
        formatted_msg = self._build_message(msg, *args, **kwargs)
        return super(ExtendedLogger, self).error(formatted_msg)

    def critical(self, msg: str, *args, **kwargs):
        """
        Override the logging.Logger.critical() method and support the formatting in self._build_message().
        """
        formatted_msg = self._build_message(msg, *args, **kwargs)
        return super(ExtendedLogger, self).critical(formatted_msg)



def logger_setup(name: str=__name__, level: int=logging.DEBUG) -> logging.Logger:
    """
    Set up standard logger.
    """
    logging.setLoggerClass(ExtendedLogger)
    logger = logging.getLogger(name)
    formatter = logging.Formatter('%(asctime)s : %(levelname)s : %(name)s : %(message)s')

    if logger.hasHandlers():
        logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.setLevel(level)
    return logger
