# vfeeg-filestor File handling for eegFaktura
# Copyright (C) 2023  Matthias Poettinger
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import logging
import traceback

from fastapi import FastAPI, HTTPException
import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.schema.config import StrawberryConfig
from app.auth import gql_context
from app.graphql.schemas.mutation_schema import Mutation
from app.graphql.schemas.query_schema import Query
from app.rest.routers import filestore
from app import health
from app.access_log import AccessLogMiddleware, GraphQLOperationName
from app.config import settings

_graphql_logger = logging.getLogger("strawberry.execution")


class Schema(strawberry.Schema):
    def process_errors(self, errors, execution_context=None):
        # Only the error class, the result path and, for unexpected errors, the stack frames (code
        # lines only) — not the error text (eegfaktura-dev tracking filestore 261030-mm1).
        for error in errors:
            original = error.original_error
            expected = isinstance(original, HTTPException) and original.status_code < 500
            _graphql_logger.log(logging.WARNING if expected else logging.ERROR, "GraphQL error", extra={
                "error.type": type(original or error).__name__,
                "graphql.error.path": ".".join(str(p) for p in error.path or []) or None,
                "error.stack_trace": None if expected or original is None
                else "".join(traceback.format_tb(original.__traceback__)),
            })


schema = Schema(query=Query, mutation=Mutation, config=StrawberryConfig(auto_camel_case=True),
                extensions=[GraphQLOperationName])


def create_app():
    app = FastAPI()
    graphql_app = GraphQLRouter(
        schema,
        context_getter=gql_context,
        graphql_ide="graphiql" if settings.GRAPHIQL_ENABLED else None,
        # Strawberry disables GraphQL multipart file uploads by default since ~0.236
        # (CSRF hardening); the filestore's add_file mutation depends on them, so
        # re-enable explicitly. Without this, uploads fail with "Unsupported content type".
        multipart_uploads_enabled=True,
    )
    app.include_router(filestore.router, prefix=f"/{settings.HTTP_FILE_DL_ENDPOINT}")
    app.include_router(graphql_app, prefix="/graphql")
    app.include_router(health.router)
    app.add_middleware(AccessLogMiddleware)
    return app
