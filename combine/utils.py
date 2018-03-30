import pathlib
import threading

from lain import ErrorModel


def model_path(root, user):
    """Return the path to a user's model.

    Parameters
    ----------
    root : path-like
        The root model directory.
    user : str
        The user to get the model path for.

    Returns
    -------
    model_path : pathlib.Path
        The path to the user's model.
    """
    root = pathlib.Path(root)
    return root / user / str(ErrorModel.version)


def instance(cls):
    """Create a new instance of a class.

    Parameters
    ----------
    cls : type
        The class to create an instance of.

    Returns
    -------
    instance : cls
        A new instance of ``cls``.
    """
    return cls()


class LockedIterator:
    """A thread-safe iterator that locks access to the underlying iterator
    when next is called.

    Parameters
    ----------
    iterator : Iterable
        The underlying iterator.
    """
    def __init__(self, iterator):
        self._iterator = iter(iterator)
        self._lock = threading.Lock()

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            return next(self._iterator)
