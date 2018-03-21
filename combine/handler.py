import datetime
from functools import lru_cache, wraps
from itertools import combinations, chain
import pathlib
import random
import re
import threading

from cryptography.fernet import Fernet
from lain import ErrorModel
import numpy as np
from slider import GameMode, Mod
from slider.client import ApprovedState

from .expiring_cache import ExpiringCache
from .format_result import format_result
from .logging import log, log_duration
from .token import gen_token
from .utils import LockedIterator


class _command:
    def __init__(self, names, f):
        self.names = names
        self.f = f


def command(*names):
    """Register a command with the handler.

    Parameters
    ----------
    *names : Iterable[str]
        The names to register the command under.
    """
    def dec(f):
        return _command(names, f)

    return dec


class _periodic_task:
    def __init__(self, time, function):
        self._time = time.total_seconds()
        self._function = function

    def run(self, *args, **kwargs):
        underlying_function = self._function

        def wrapped_function(*args, **kwargs):
            underlying_function(*args, **kwargs)
            start()

        def start():
            threading.Timer(self._time, wrapped_function, args, kwargs).start()

        start()


def periodic_task(time):
    """A periodic task is scheduled by the client to be run about every n
    periods.

    Parameters
    ----------
    time : datetime.timedelta
        The delay between calls.
    """
    def dec(f):
        return _periodic_task(time, f)

    return dec


class CommandFailure(Exception):
    """Exception raised to indicate that a command failed.
    """


class Handler:
    """Abstract command handler.

    Parameters
    ----------
    channels : iterable[str]
        The names of the channels to listen to.

    To implement a handler, subclass this class and decorate handling methods
    with :func:`~combine.handler.command` passing the name and aliases of the
    command.
    """
    def __init__(self, channels):
        self._channels = frozenset(channels)

    _commands = {}
    _periodic_tasks = []

    def __init_subclass__(cls):
        cls._commands = super(cls, cls)._commands.copy()
        cls._periodic_tasks = super(cls, cls)._periodic_tasks.copy()
        for k, v in vars(cls).items():
            if isinstance(v, _command):
                for name in v.names:
                    cls._commands[name] = v.f
            elif isinstance(v, _periodic_task):
                cls._periodic_tasks.append(v)

    @staticmethod
    def send(client, user, msg):
        """Send a message to the client.

        Parameters
        ----------
        client : Client
            The client to send a message to.
        user : User
            The user to send the message to.
        msg : str
            The message to send.

        Notes
        -----
        This is implemented as a method to allow subclasses to hook into
        how messages are sent.
        """
        return client.send(user, msg)

    def should_handle_message(self, user, channel):
        """A predicate for filtering out messages which can be overridden
        by concrete handlers.

        Parameters
        ----------
        user : str
            The user who sent the message.
        channel : str
            The channel the message was sent on.

        Returns
        -------
        should_handle_message : bool
            Should the message be handled?
        """
        return channel in self._channels

    def __call__(self, client, user, channel, msg):
        if not self.should_handle_message(user, channel):
            return

        split = msg.split(' ', 1)
        if not split:
            return

        command = split[0]
        if len(split) == 1:
            data = ''
        else:
            data = split[1]

        try:
            f = self._commands[command]
        except KeyError:
            return

        try:
            f(self, client, user, data)
        except CommandFailure as e:
            self.send(client, user, f'Error: {e}')


def powerset(values):
    return chain.from_iterable(
        combinations(values, n) for n in range(len(values) + 1),
    )


class CombineHandler(Handler):
    """Concrete handler for the combine irc server.

    Parameters
    ----------
    bot_user : str
        The username of the bot itself.
    osu_client : slider.Client
        The osu rest client.
    model_cache_dir : path-like
        The path to the directory of models for every user.
    model_cache_size : int or None
        The number of models to hold in memory at once. None will hold all
        models in memory.
    token_secret : bytes
        The secret key for generating tokens.
    upload_url : str
        The url to upload replays.
    train_queue : TrainQueue
        The queue to read training results out of.
    """
    # the weights for the top 100 scores
    _pp_weights = 0.95 ** np.arange(100)
    _user_stats_cache_lifetime = datetime.timedelta(hours=2)
    _pp_curve_accuracies = np.array([0.95, 0.96, 0.97, 0.98, 0.99, 1.00])

    def __init__(self,
                 bot_user,
                 osu_client,
                 model_cache_dir,
                 model_cache_size,
                 token_secret,
                 upload_url,
                 train_queue):
        super().__init__({bot_user})

        self.bot_user = bot_user
        self._root_osu_client = osu_client
        self.model_cache_dir = pathlib.Path(model_cache_dir)
        self.token_secret = Fernet(token_secret)
        self.upload_url = upload_url
        self.train_queue = train_queue

        self.get_model = lru_cache(model_cache_size)(self._get_model)
        self._user_stats = ExpiringCache()

        self._candidates = LockedIterator(self._gen_candidates())

        self._tls = threading.local()

    @property
    def osu_client(self):
        """A thread-local :class:`slider.Client`.
        """
        try:
            osu_client = self._tls.osu_client
        except AttributeError:
            osu_client = self._tls.osu_client = self._root_osu_client.copy()

        return osu_client

    @periodic_task(datetime.timedelta(seconds=30))
    def report_training_status(self, client):
        """Every 30 seconds, check the database to see if we have any new
        results to report and send them to users.
        """
        for user, status in self.train_queue.copy().get_completed_jobs():
            self.send(
                client,
                user,
                f'model training complete: {status.value}',
            )

    def _get_model(self, user):
        try:
            return ErrorModel.load_path(self.model_cache_dir / user)
        except FileNotFoundError:
            raise KeyError(user)

    def _gen_candidates(self):
        candidates = []
        while True:
            if not candidates:
                since = datetime.datetime.now() - datetime.timedelta(days=365)
                # pull all the candidates in the same thread while we hold
                # a lock
                raw_candidates = self.osu_client.beatmap(
                    limit=500,
                    game_mode=GameMode.standard,
                    since=since,
                )
                candidates = []
                for raw_candidate in raw_candidates:
                    if raw_candidate.approved != ApprovedState.ranked:
                        continue

                    try:
                        beatmap = raw_candidate.beatmap(save=True)
                    except Exception:
                        log.exception(
                            'failed to parse beatmap {raw_candidate}',
                            raw_candidate,
                        )
                        continue

                    if len(beatmap.hit_objects) >= 2:
                        candidates.append(beatmap)

                random.shuffle(candidates)

            yield candidates.pop()

    _mods = {
        'hard_rock': 'HR',
        'double_time': 'DT',
        'half_time': 'HT',
        'hidden': 'HD',
    }
    _mod_powerset = list(powerset(_mods))

    def _predict(self, user, model, beatmap, with_mods, without_mods):
        """
        """
        all_mods = self._mods
        mod_masks = (
            {k: (k in mods) for k in all_mods}
            for mods in self._mod_powerset
            # enforce the pinned mods
            if all(k in mods for k in with_mods) and
            not any(k in mods for k in without_mods)
        )

        try:
            return [
                (mod_mask, model.predict(beatmap, **mod_mask))
                for mod_mask in mod_masks
            ]
        except Exception:
            log.exception(
                'failed to predict beatmap {beatmap}, user={user}',
                beatmap=beatmap,
                user=user,
            )
            return []

    def _parse_recommend_args(self, msg):
        args = msg.strip().split()

        with_mods = set()
        without_mods = set()
        for arg in args:
            set_ = with_mods
            if arg[0] == '+':
                arg = arg[1:]
            elif arg[0] == '-':
                set_ = without_mods
                arg = arg[1:]

            try:
                mods = Mod.parse(arg.lower())
            except ValueError as e:
                raise CommandFailure(f'failed to parse mods from {msg!r}: {e}')

            unpacked = Mod.unpack(mods)
            for mod in self._mods:
                if unpacked[mod]:
                    set_.add(mod)

        return with_mods, without_mods

    _no_model_message = (
        "I haven't trained a model for you yet. Please go to {url} and upload"
        " your replays. To associate the replays with your account, send me"
        " the command `!gen-token` and enter that along with your replays."
    )

    def _log_duration(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            with log_duration(f.__name__, level='debug'):
                f(*args, **kwargs)

        return wrapper

    @command('!r', '!rec', '!recommend')
    @_log_duration
    def recommend(self, client, user, msg):
        """Recommend a beatmap for the user.
        """
        try:
            model = self.get_model(user)
        except KeyError:
            raise CommandFailure(
                self._no_model_message.format(user=user, url=self.upload_url)
            )

        try:
            lower_bound, upper_bound = self._user_stats[user]
        except KeyError:
            pp = np.array([
                hs.pp
                for hs in self.osu_client.user_best(user_name=user, limit=100)
            ])
            # Take a weighted average of the PP weighing by the contribution to
            # ranked PP. Slice the weight vector in case the user has less than
            # 100 high scores.
            user_average = np.average(pp, weights=self._pp_weights[:len(pp)])
            lower_bound = user_average - pp.std()
            # The model isn't very accurate for really hard maps it hasn't seen
            # This keeps the suggestions reasonable.
            upper_bound = pp.max() + (pp.std() / 2)

            # cache the PP lookup for a while
            self._user_stats[user] = (
                (lower_bound, upper_bound),
                datetime.datetime.now() + self._user_stats_cache_lifetime,
            )

        with_mods, without_mods = self._parse_recommend_args(msg)

        for n, beatmap in enumerate(self._candidates):
            if n > 50:
                break

            predictions = self._predict(
                user,
                model,
                beatmap,
                with_mods,
                without_mods,
            )
            for mask, prediction in predictions:
                if (lower_bound <= prediction.pp_mean <= upper_bound and
                        prediction.accuracy_mean >= 0.95):
                    if not any(mask.values()):
                        mods = ''
                    else:
                        mods = ' with ' + ''.join(sorted(
                            self._mods[k] for k, v in mask.items() if v
                        ))

                    log.info(
                        'recommending {user} {beatmap.display_name} {mods}',
                        user=user,
                        beatmap=beatmap,
                        mods=mods,
                    )
                    return self.send(
                        client,
                        user,
                        format_result(
                            beatmap,
                            mods,
                            prediction,
                            show_link=True,
                        ),
                    )

        raise CommandFailure('not enough candidate beatmaps, try again later')

    @command('!gen-token')
    def gen_token(self, client, user, msg):
        """Generate a token for the user using the ``token_secret``.
        """
        if msg:
            raise CommandFailure(f'gen-token takes no arguments, got: {msg!r}')

        self.send(client, user, f'token: {gen_token(self.token_secret, user)}')
        self.send(
            client,
            user,
            'To copy the token, type `/savelog` and then  navigate to your'
            ' osu!/Chat directory and open the newest file.'
        )

    _np_pattern = re.compile(
        r'is listening to \[https://osu.ppy.sh/b/(\d+)',
    )

    @command('\x01ACTION')
    def np(self, client, user, msg):
        match = self._np_pattern.match(msg)
        if match is None:
            return

        beatmap = self.osu_client.beatmap(
            beatmap_id=match.groups(1),
        ).beatmap(save=True)

        pp_curve = beatmap.performance_points(
            accuracy=self._pp_curve_accuracies,
        )

        try:
            model = self.get_model(user)
        except KeyError:
            self.send(
                client,
                user,
                self._no_model_message.format(user=user, url=self.upload_url),
            )
            prediction = None
        else:
            prediction = model.predict(beatmap)

        self.send(
            client,
            user,
            format_result(
                beatmap,
                '',
                prediction,
                pp_curve,
                show_link=True,
            ),
        )


class ReplCombineHandler(CombineHandler):
    """A :class:`~combine.handler.CombineHandler` which only listens
    to messages from the bot user and echos responses to the terminal.
    """
    def should_handle_message(self, user, channel):
        return user == channel == self.bot_user

    def send(self, client, user, msg):
        print(msg)
        super().send(client, user, msg)
