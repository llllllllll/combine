import datetime
from functools import lru_cache
from itertools import combinations, chain
import json
import pathlib
import pickle
import random

from cryptography.fernet import Fernet
import numpy as np
import pandas as pd
from slider import GameMode, Mod
from slider.client import ApprovedState

from .token import gen_token


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

    def __init_subclass__(cls):
        cls._commands = super(cls, cls)._commands.copy()
        for k, v in vars(cls).items():
            if isinstance(v, _command):
                for name in v.names:
                    cls._commands[name] = v.f

    def __call__(self, client, user, channel, msg):
        if channel not in self._channels:
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
            client.send(user, f'Error: {e}')


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
    """
    def __init__(self,
                 bot_user,
                 osu_client,
                 model_cache_dir,
                 model_cache_size,
                 token_secret,
                 upload_url):
        super().__init__({bot_user})

        self.bot_user = bot_user
        self.osu_client = osu_client
        self.model_cache_dir = pathlib.Path(model_cache_dir)
        self.token_secret = Fernet(token_secret)
        self.upload_url = upload_url

        self.get_model = lru_cache(model_cache_size)(self._get_model)
        self._user_stats = {}

        self._candidates = self._gen_candidates()

    def _get_model(self, user):
        try:
            with open(self.model_cache_dir / user, 'rb') as f:
                return pickle.load(f)
        except FileNotFoundError:
            raise KeyError(user)

    def _gen_candidates(self):
        since = datetime.datetime.now() - datetime.timedelta(days=365)
        candidates = None
        while True:
            if not candidates:
                candidates = self.osu_client.beatmap(
                    limit=500,
                    game_mode=GameMode.standard,
                    since=since,
                )
                random.shuffle(candidates)

            candidate = candidates.pop()
            if (candidate.approved == ApprovedState.ranked and
                    len(candidate.beatmap.hit_objects) >= 2):
                yield candidate

    @staticmethod
    def _format_link(beatmap):
        """Format a beatmap link to send back to the user.

        Parameters
        ----------
        beatmap : Beatmap
            The beatmap to format.

        Returns
        -------
        link : str
             The link to send back.
        """
        return (
            f'[https://osu.ppy.sh/b/{beatmap.beatmap_id}'
            f' {beatmap.artist} -'
            f' {beatmap.title} [{beatmap.version}]]'
        )

    _mods = {
        'hard_rock': 'HR',
        'double_time': 'DT',
        'hidden': 'HD',
    }
    _mod_powerset = list(powerset(_mods))

    def _predict(self, model, beatmap, with_mods, without_mods):
        """
        """
        all_mods = self._mods
        mod_masks = [
            {k: (k in mods) for k in all_mods}
            for mods in self._mod_powerset
            # enforce the pinned mods
            if all(k in mods for k in with_mods) and
            not any(k in mods for k in without_mods)
        ]

        try:
            accuracy = model.predict_beatmap(beatmap, *mod_masks)
        except ValueError:
            return ()

        pp = (
            beatmap.performance_points(accuracy=acc, **mask)
            for acc, mask in zip(accuracy, mod_masks)
        )
        return zip(mod_masks, accuracy, pp)

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

    @command('!r', '!rec', '!recommend')
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
            user_average, user_std, user_max = self._user_stats[user]
        except KeyError:
            pp = np.array([
                hs.pp
                for hs in self.osu_client.user_best(user_name=user, limit=100)
            ])
            user_average, user_std, user_max = self._user_stats[user] = (
                pp.mean(),
                pp.std(),
                pp.max()
            )

        with_mods, without_mods = self._parse_recommend_args(msg)

        # The model isn't very accurate for really hard maps it hasn't seen
        # This keeps the suggestions reasonable.
        upper = user_max + (user_std / 2)

        for candidate in self._candidates:
            beatmap = candidate.beatmap
            predictions = self._predict(
                model,
                beatmap,
                with_mods,
                without_mods,
            )
            for mask, accuracy, pp in predictions:
                if user_average <= pp <= upper and accuracy > 0.95:
                    if not any(mask.values()):
                        mods = ''
                    else:
                        mods = ' with ' + ''.join(sorted(
                            self._mods[k] for k, v in mask.items() if v
                        ))

                    return client.send(
                        user,
                        f'{self._format_link(beatmap)} '
                        f'{mods} '
                        f'predicted: {accuracy * 100:.2f}% | {pp:.2f}pp'
                    )

        raise CommandFailure('not enough candidate beatmaps, try again later')

    @command('!gen-token')
    def gen_token(self, client, user, msg):
        """Generate a token for the user using the ``token_secret``.
        """
        if msg:
            raise CommandFailure(f'gen-token takes no arguments, got: {msg!r}')

        client.send(user, f'token: {gen_token(self.token_secret, user)}')
        client.send(
            user,
            'To copy the token, type `/savelog` and then  navigate to your'
            ' osu!/Chat directory and open the newest file.'
        )
