import datetime
from functools import lru_cache
from itertools import combinations, chain
import pathlib
import pickle
import random

import numpy as np
from slider import GameMode
from slider.client import ApprovedState


class _command:
    def __init__(self, names, f):
        self.names = tuple('!' + name for name in names)
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
            f(self, client, user, channel, data)
        except CommandFailure as e:
            client.send(user, f'Error: {e}')


def powerset(values):
    return chain.from_iterable(
        combinations(values, n) for n in range(len(values) + 1),
    )


class CombineHandler(Handler):
    def __init__(self,
                 bot_user,
                 osu_client,
                 model_cache_dir,
                 model_cache_size,
                 token_secret):
        super().__init__({bot_user})

        self.bot_user = bot_user
        self.osu_client = osu_client
        self.model_cache_dir = pathlib.Path(model_cache_dir)
        self.token_secret = token_secret

        self.get_model = lru_cache(model_cache_size)(self._get_model)
        self._user_average = {}

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

    def _predict_all_mods(self, model, beatmap):
        all_mods = self._mods
        mod_masks = [
            {k: (k in mods) for k in all_mods} for mods in self._mod_powerset
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

    @command('r', 'rec', 'recommend')
    def recommend(self, client, user, channel, msg):
        if msg:
            raise CommandFailure(f'recommend takes no arguments, got: {msg!r}')

        try:
            model = self.get_model(user)
        except KeyError:
            raise CommandFailure(
                f'no model found for {user}, send me your replays',
            )

        try:
            user_average = self._user_average[user]
        except KeyError:
            user_average = self._user_average[user] = np.mean([
                hs.pp
                for hs in self.osu_client.user_best(user_name=user, limit=100)
            ])

        for candidate in self._candidates:
            beatmap = candidate.beatmap
            for mask, accuracy, pp in self._predict_all_mods(model, beatmap):
                if pp > user_average and accuracy > 0.95:
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
