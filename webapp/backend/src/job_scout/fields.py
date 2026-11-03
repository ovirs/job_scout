"""Field types the request schemas of several packages share."""

from typing import Annotated

from pydantic import StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
