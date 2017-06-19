from collections import namedtuple
import datetime
import json
import pathlib
import pickle

from cryptography.fernet import Fernet
import flask
from gunicorn.app.base import BaseApplication
import numpy as np
import pandas as pd
from slider import Replay, GameMode
from slider.client import UnknownBeatmap
from slider.model import extract_feature_array, train_model

from .logging import log


api = flask.Blueprint('combine-uploader', __name__)
_app_data = {}


AppData = namedtuple(
    'AppData',
    'model_cache_dir token_secret client index_html',
)


def _register_api(app, options, first_registration=False):
    _app_data[app] = AppData(
        options['model_cache_dir'],
        options['token_secret'],
        options['client'],
        index_html_template.format(
            github_url=options['github_url'],
            email_address=options['email_address'],
            bot_user=options['bot_user'],
        ),
    )

    # Call the original register function.
    flask.Blueprint.register(api, app, options, first_registration)


api.register = _register_api


index_html_template = """
<!DOCTYPE html>
<h1>
  <a href={github_url} target="_blank">
    combine
  </a>
</h1>

<h2>
  If you want to make this page not look terrible please email me at
  {email_address}!
<h2>

<form action="/train" method="post" enctype=multipart/form-data>
  <fieldset>
    <legend>
      Upload your replays; it will take a while after you click submit, be
      patient
    </legend>

    <div class="form-group">
      <label for="replays">
        .osr files
      </label>
      <input name=replays type=file multiple required>
    </div>

    <div class="form-group">
      <label for="training-days">
        training period in days
      </label>
      <input name="training-days" type=number value=182 min=0 required>
    </div>

    <div class="form-group">
      <label for=token>
        secret token: get this by sending {bot_user} "!gen-token" in osu!
      </label>
      <input name="token" type=text required>
    </div>

    <div class="form-group">
      <input value="submit" type=submit>
    </div>
  </fieldset>
</form>
"""


@api.route('/')
def index():
    return _app_data[flask.current_app].index_html


@api.route('/train', methods=['POST'])
def train():
    model_cache_dir, token_secret, client, _ = _app_data[flask.current_app]
    try:
        enc_token = flask.request.form['token'].encode('ascii')
    except Exception as e:
        return f'malformed or missing token: {type(e)}: {e}', 401

    try:
        token = json.loads(token_secret.decrypt(enc_token).decode('utf-8'))
    except Exception:
        return 'failed to decrypt token', 401

    if pd.Timestamp.now(tz='utc') > pd.Timestamp(token['expires']):
        return 'expired token', 401

    user = token['user']
    age = flask.request.form.get('training-days', None)
    if age:
        try:
            days = int(age)
            if days < 0:
                raise ValueError()
        except ValueError:
            return 'age must be a positive integer', 400

        age = datetime.timedelta(days=days)
    else:
        age = None

    try:
        model = train_from_form(
            flask.request.files.getlist('replays'),
            client,
            age,
        )
    except Exception as e:
        log.exception('failed to train')
        return f'failed to train: {type(e)}: {e}', 400

    with open(model_cache_dir / user, 'wb') as f:
        pickle.dump(model, f)

    return 'model trained! you may now ask for recommendations with !r'


def extract_from_form(files, client, age):
    """Extract features from the files uploaded.

    Parameters
    ----------
    files : Iterable[FileStorage]
        Files uploaded in the form.
    client : Client
        The client used to fetch beatmaps.
    age : datetime.timedelta, optional
        Only count replays less than this age old.

    Returns
    -------
    features : np.ndarray[float]
        The array of input data with one row per play.
    accuracies : np.ndarray[float]
        The array of accuracies achieved on each of the beatmaps in
        ``features``.

    Notes
    -----
    The same beatmap may appear more than once if there are multiple replays
    for this beatmap.
    """
    beatmaps_and_mods = []
    accuracies = []

    beatmap_and_mod_append = beatmaps_and_mods.append
    accuracy_append = accuracies.append

    for entry in files:
        if not entry.filename.endswith('.osr'):
            continue

        try:
            replay = Replay.parse(entry.read(), client=client, save=True)
        except Exception:
            continue

        if (age is not None and
                datetime.datetime.utcnow() - replay.timestamp > age):
            continue

        if (replay.mode != GameMode.standard or
                replay.autoplay or
                replay.auto_pilot or
                replay.cinema or
                replay.relax or
                len(replay.beatmap.hit_objects) < 2):
            # ignore plays with mods that are not representative of user skill
            continue

        beatmap_and_mod_append((
            replay.beatmap, {
                'easy': replay.easy,
                'hidden': replay.hidden,
                'hard_rock': replay.hard_rock,
                'double_time': replay.double_time,
                'half_time': replay.half_time,
                'flashlight': replay.flashlight,
            },
        ))
        accuracy_append(replay.accuracy)

    if not beatmaps_and_mods:
        return np.array([]), np.array([])

    fs = extract_feature_array(beatmaps_and_mods)
    mask = np.isfinite(fs).all(axis=1)
    return fs[mask], np.array(accuracies)[mask]


def train_from_form(files, client, age):
    """Train a model from uploaded form files.

    Parameters
    ----------
    files : Iterable[FileStorage]
        Files uploaded in the form.
    client : Client
        The client used to fetch beatmaps.
    age : datetime.timedelta, optional
        Only count replays less than this age old.

    Returns
    -------
    model : Regressor
        The scikit-learn model fit with the input data. New observations can
        be added by re-fitting the new replays.

    Notes
    -----
    The same beatmap may appear more than once if there are multiple replays
    for this beatmap.
    """
    labels, acc = extract_from_form(files, client, age)
    if not len(labels):
        raise ValueError('no valid replays found')
    return train_model(labels, acc)


def build_app(model_cache_dir,
              token_secret,
              client,
              bot_user,
              github_url,
              email_address,
              gunicorn_options):
    """Build the app object.

    Parameters
    ----------
    model_cache_dir : path-like
        The path to the model directory.
    token_secret : bytes
        The shared secret for the uploader and irc server.
    client : Library
        The client used to fetch beatmaps.
    bot_user : str
        The username of the bot.
    github_url : str
        The url of the repo on github.
    email_address : str
        The email address for support / comments.
    gunicorn_options : dict
        Options to forward to gunicorn.

    Returns
    -------
    app : App
        The app to run.
    """
    inner_app = flask.Flask(__name__)
    inner_app.register_blueprint(
        api,
        model_cache_dir=pathlib.Path(model_cache_dir),
        token_secret=Fernet(token_secret),
        client=client,
        bot_user=bot_user,
        github_url=github_url,
        email_address=email_address,
    )

    class app(BaseApplication):
        def load(self):
            return inner_app

        def load_config(self, *, _cfg=gunicorn_options):
            for k, v in _cfg.items():
                k = k.lower()
                if k in self.cfg.settings and v is not None:
                    self.cfg.set(k.lower(), v)

    return app()
