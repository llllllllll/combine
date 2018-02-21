import datetime
import json
import os

import flask
import pandas as pd
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


@api.route('/train', methods=['POST'])
def train():
    try:
        enc_token = flask.request.form['token'].encode('ascii')
    except Exception as e:
        return f'malformed or missing token: {type(e)}: {e}', 401

    try:
        token = json.loads(
            flask.g.token_secret.decrypt(enc_token).decode('utf-8'),
        )
    except Exception:
        return 'failed to decrypt token', 401

    if pd.Timestamp.now(tz='utc') > pd.Timestamp(token['expires']):
        return 'expired token', 401

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

    for file in flask.request.files.getlist('replays'):
        filename = secure_filename(file.filename)
        file.save(os.fspath(flask.g.replay_cache_dir / user / filename))

    flask.g.train_queue.enqueue_job(user, age)
    flask.flash(
        f'Your model is being trained, message {flask.g.bot_user} will message'
        ' you when your model is done training or if an error occurs.',
    )
    return flask.redirect(flask.url_for('combine-uploader.index'))
