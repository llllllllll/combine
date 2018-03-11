import json

import pandas as pd


def gen_token(token_secret, user, *, expires=None):
    """Generate a token for a user.

    Parameters
    ----------
    token_secret : secret
        The secret to encrypt with.
    user : str
        The user to make a token for.
    expires : pd.Timestamp, optional
        The expiration time. If not provided, the token will be valid for 12
        hours.

    Returns
    -------
    token : str
        The encrypted token.
    """
    now = pd.Timestamp.now(tz='utc')

    if expires is None:
        expires = (now + pd.Timedelta(hours=12))

    return token_secret.encrypt(
        json.dumps({
            'issued': now.isoformat(),
            'expires': expires.isoformat(),
            'user': user,
        }).encode('utf-8')
    ).decode('utf-8')
