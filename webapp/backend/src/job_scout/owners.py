"""Who owns the data a request touches.

There is no login while the app runs locally: every request acts as the single
local user. Every user-owned table still carries an owner column, so a later
login only has to change `current_owner`.
"""

import uuid

LOCAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def current_owner() -> uuid.UUID:
    return LOCAL_USER_ID
