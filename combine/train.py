from enum import unique, Enum
import os
import sqlite3
import subprocess
import sys
from time import sleep

from .logging import log
from . import _train_runner


@unique
class Status(Enum):
    """The status of a job.
    """
    not_started = 'not started'
    running = 'running'
    failed = 'failed'
    success = 'success'


class TrainQueue:
    """A queue of training work to be done.

    Parameters
    ----------
    train_queue_db : path-like
        The underlying queue database path.
    """
    def __init__(self, train_queue_db_path):
        self._db_path = train_queue_db_path
        self._db = sqlite3.connect(os.fspath(train_queue_db_path))
        self._db.execute(
            """
            create table if not exists queue (
                user string not null,
                age str not null,
                status string not null,
                insert_time int not null,
                reported bool not null
            )
            """,
        )

    def copy(self):
        """Create a copy suitable for use in a new thread.

        Returns
        -------
        TrainQueue
            The new copy.
        """
        return type(self)(self._db_path)

    def enqueue_job(self, user, age):
        """Enqueue a new job to run when there is time available.

        Parameters
        ----------
        user : str
            The user to train for.
        age : datetime.timedelta or None
            The age threshold in days for training.
        """
        self._db.execute(
            "insert into queue values (?, ?, ?, datetime('now'), 0)",
            (user, str(age), Status.not_started.value),
        )
        self._db.commit()

    class Empty(Exception):
        pass

    def get_job(self):
        """Get a job from the queue, if no jobs are waiting to be run, raise
        ``Empty``.
        """
        results = list(self._db.execute(
            'select rowid, user, age from queue where status=?'
            ' order by insert_time limit 1',
            (Status.not_started.value,),
        ))
        if not results:
            raise self.Empty()

        return results[0]

    def get_completed_jobs(self):
        """Get all of the completed jobs that have not been reported.

        Returns
        -------
        completed : list[(str, str)]
            A list of (user name, status) pairs for each newly completed task.
        """
        results = self._db.execute(
            """
            select rowid, user, status from queue
            where not reported and (status == ? or status == ?)
            """,
            (Status.success.value, Status.failed.value)
        )
        out = []
        for rowid, user, status in results:
            out.append((user, Status(status)))
            self._db.execute(
                'update queue set reported=1 where rowid=?',
                (rowid,),
            )

        self._db.commit()
        return out

    def update_status(self, rowid, status):
        """Update the status of a job.

        Parameters
        ----------
        rowid : int
            The row id returned from ``get``.
        status : Status
            The new status to set.
        """
        self._db.execute(
            'update queue set status=? where rowid=?',
            (status.value, rowid),
        )
        self._db.commit()


def _run_train_job(user, age_str, replay_cache_dir, model_cache_dir, client):
    log.info('starting train job for user: {user}', user=user)
    args = [
        sys.executable, '-m', _train_runner.__name__,
        '--user', user,
        '--replay-cache-dir', os.fspath(replay_cache_dir),
        '--model-cache-dir', os.fspath(model_cache_dir),
        '--library', client.library.path,
        '--api-key', client.api_key,
    ]

    if age_str is not None:
        args.extend((
            '--age', age_str
        ))

    result = subprocess.run(
        args,
        stderr=subprocess.PIPE,
        encoding='utf-8',
    )
    failed = result.returncode != 0
    if failed:
        log.error(
            'failed train job for user: {user}\n{stderr}',
            user=user,
            stderr=result.stderr,
        )
    return failed


def run_train_queue(train_queue,
                    replay_cache_dir,
                    model_cache_dir,
                    client):
    """Run the train queue for ever, popping jobs and training the model
    for the user.

    Parameters
    ----------
    train_queue : TrainQueue
        The train queue to pop from.
    replay_cache_dir : path-like
        The root directory for all replays.
    model_cache_dir : path-like
        The root directory for all models.
    client : slider.Client
        The slider client to use when parsing replays.
    """
    while True:
        try:
            rowid, user, agestr = train_queue.get_job()
        except TrainQueue.Empty:
            log.debug('no jobs')
            sleep(1)
            continue

        train_queue.update_status(rowid, Status.running)
        try:
            failed = _run_train_job(
                user,
                agestr,
                replay_cache_dir,
                model_cache_dir,
                client,
            )
        except Exception:
            failed = True
            log.exception('failed to train for user: {user}', user=user)
        finally:
            train_queue.update_status(
                rowid,
                Status.failed if failed else Status.success,
            )
