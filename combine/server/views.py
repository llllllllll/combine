import datetime
import json
import os

import flask
from lain import LSTM
import pandas as pd
from slider.mod import Mod
from werkzeug import secure_filename

api = flask.Blueprint('combine-uploader', __name__)


@api.route('/')
def index():
    return flask.render_template(
        'index.html',
        github_url=flask.g.github_url,
        email_address=flask.g.email_address,
        bot_user=flask.g.bot_user,
    )


class ExpiredToken(Exception):
    """Raised when a token has expired.
    """


def read_token(enc_token):
    """Read the encrypted token and ensure that it has not expired.

    Parameters
    ----------
    enc_token : str
        The encrypted token.

    Returns
    -------
    token : dict[str, str]
        The unencrypted token.

    Raises
    ------
    ValueError
        Raised when the token is malformed or cannot be decrypted.
    ExpiredToken
        Raised when the token has expired.
    """
    try:
        token = json.loads(
            flask.g.token_secret.decrypt(
                enc_token.encode('ascii'),
            ).decode('utf-8'),
        )
    except Exception as e:
        raise ValueError(f'failed to decrpyt token: {e}')

    if token.keys() != {'issued', 'expires', 'user'}:
        raise ValueError('malformed token')

    if pd.Timestamp.now(tz='utc') > pd.Timestamp(token['expires']):
        raise ExpiredToken()

    return token


@api.route('/train', methods=['POST'])
def train():
    try:
        enc_token = flask.request.form['token']
    except Exception as e:
        return f'malformed or missing token: {type(e)}: {e}', 401

    try:
        token = read_token(enc_token)
    except ExpiredToken:
        return 'expired token', 401
    except Exception as e:
        return str(e), 400

    user = token['user']
    age = flask.request.form.get('training-days', None)
    if age:
        try:
            age = int(age)
            if age < 0:
                raise ValueError()

            age = datetime.timedelta(days=age)
        except ValueError:
            return 'age must be a positive integer', 400
    else:
        age = None

    user_replays = flask.g.replay_cache_dir / user
    user_replays.mkdir(exist_okay=True)
    for file in flask.request.files.getlist('replays'):
        filename = secure_filename(file.filename)
        file.save(os.fspath(user_replays / filename))

    flask.g.train_queue.enqueue_job(user, age)
    flask.flash(
        f'Your model is being trained, message {flask.g.bot_user} will message'
        ' you when your model is done training or if an error occurs.',
    )
    return flask.redirect(flask.url_for('combine-uploader.index'))


@api.route('/api/predict')
def predict():
    try:
        token = read_token(flask.request.args['token'])
    except ExpiredToken:
        return 'expired token', 401
    except Exception as e:
        return str(e), 400

    try:
        beatmap_id = flask.request.args['beatmap_id']
    except KeyError:
        return 'missing beatmap_id argument', 400

    try:
        beatmap = flask.g.client.library.lookup_by_id(
            beatmap_id,
            download=True,
            save=True,
        )
    except KeyError:
        return f'unknown beatmap: {beatmap_id}', 400

    mods = flask.request.args.get('mods', '')
    try:
        unpacked = Mod.unpack(Mod.parse(mods))
    except ValueError as e:
        return str(e), 400

    mod_kwargs = {
        'hard_rock': unpacked.pop('hard_rock'),
        'double_time': unpacked.pop('double_time'),
        'hidden': unpacked.pop('hidden'),
    }

    if any(unpacked.values()):
        return 'only HD, HR, and DT can be used', 400

    try:
        model = flask.g.get_model(token['user'])
    except KeyError:
        return 'no model trained', 404

    accuracy = model.predict_beatmap(beatmap, **mod_kwargs).item()

    return flask.jsonify({
        'accuracy': accuracy,
        'performance_points': beatmap.performance_points(
            accuracy=accuracy,
            **mod_kwargs,
        ),
    })
