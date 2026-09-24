"""Shared query-parameter bounds, declared on the parameter itself so they
show up in the OpenAPI schema and out-of-range values get a 422 -- rather
than being silently clamped in each route body, where clients can't see them."""
from typing import Annotated

from fastapi import Query

PageLimit = Annotated[int, Query(ge=1, le=200)]
PageOffset = Annotated[int, Query(ge=0)]
