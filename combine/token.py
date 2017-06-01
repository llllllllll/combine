import json

import pandas as pd


def gen_token(token_secret, user):
    """Generate a token for a user.

    Parameters
    ----------
    token_secret : secret
        The secret to encrypt with.
    user : str
        The user to make a token for.

    Returns
    -------
    token : str
        The encrypted token.
    """
    now = pd.Timestamp.now(tz='utc')
    return token_secret.encrypt(
        json.dumps({
            'issued': now.isoformat(),
            'expires': (now + pd.Timedelta(hours=12)).isoformat(),
            'user': user,
        }).encode('utf-8')
    ).decode('utf-8')
