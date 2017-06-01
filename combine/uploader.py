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
from slider.model import extract_feature_array, train_model


api = flask.Blueprint('combine-uploader', __name__)
_app_data = {}


def _register_api(app, options, first_registration=False):
    _app_data[app] = (
        options['model_cache_dir'],
        options['token_secret'],
        options['library'],
    )

    # Call the original register function.
    flask.Blueprint.register(api, app, options, first_registration)


api.register = _register_api


index_html = """
<!DOCTYPE html>
<h1>
  <a href="https://github.com/llllllllll/combine" target="_blank">
    combine
  </a>
</h1>

<h2>
  If you want to make this page not look terrible please email me at
  joejev@gmail.com!
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
        secret token: get this by sending JoeJev "!gen-token" in osu!
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
    return index_html


@api.route('/train', methods=['POST'])
def train():
    model_cache_dir, token_secret, library = _app_data[flask.current_app]
    try:
        token = json.loads(token_secret.decrypt(
            flask.request.form['token'].encode('ascii'),
        ).decode('utf-8'))

        if pd.Timestamp.now(tz='utc') > pd.Timestamp(token['expires']):
            return 'expired token', 401

        user = token['user']
    except Exception as e:
        return 'bad token', 401

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

    model = train_from_form(
        flask.request.files.getlist('replays'),
        library,
        age,
    )
    with open(model_cache_dir / user, 'wb') as f:
        pickle.dump(model, f)

    return 'model trained! you may now ask for recommendations with !r'


def extract_from_form(files, library, age):
    """Extract features from the files uploaded.

    Parameters
    ----------
    files : Iterable[FileStorage]
        Files uploaded in the form.
    library : Library
        The beatmap library to use when parsing the replays.
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

        replay = Replay.parse(entry.read(), library=library)
        if (age is not None and
                datetime.datetime.utcnow() - replay.timestamp > age):
            continue

        if (replay.mode != GameMode.standard or
                replay.autoplay or
                replay.spun_out or
                replay.auto_pilot or
                replay.cinema or
                replay.relax):
            # ignore plays with mods that are not representative of user skill
            continue

        if len(replay.beatmap.hit_objects) < 2:
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

    fs = extract_feature_array(beatmaps_and_mods)
    mask = np.isfinite(fs).all(axis=1)
    return fs[mask], np.array(accuracies)[mask]


def train_from_form(files, library, age):
    """Train a model from uploaded form files.

    Parameters
    ----------
    files : Iterable[FileStorage]
        Files uploaded in the form.
    library : Library
        The beatmap library to use when parsing the replays.
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
    return train_model(*extract_from_form(files, library, age))


def build_app(model_cache_dir, token_secret, library, gunicorn_options):
    """Build the app object.

    Parameters
    ----------
    model_cache_dir : path-like
        The path to the model directory.
    token_secret : bytes
        The shared secret for the uploader and irc server.
    library : Library
        The beatmap library.
    gunicorn_options : dict
        Options to forward to gunicorn

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
        library=library,
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
