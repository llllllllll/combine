combine
=======

IRC bot for suggesting beatmaps based on your replay data.

Usage
-----

.. code-block:: bash

   $ python -m combine serve


Serve the irc bot. Hitting enter in the terminal will send yourself a
recommendation because you cannot message yourself in the osu! client.

.. code-block:: bash

   $ python -m combine train

Train the model with a given user's data so that they may ask for
recommendations.
