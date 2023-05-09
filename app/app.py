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

from fastapi import FastAPI
import strawberry
from strawberry.fastapi import GraphQLRouter
from strawberry.schema.config import StrawberryConfig
from app.graphql.schemas.mutation_schema import Mutation
from app.graphql.schemas.query_schema import Query
from app.rest.routers import filestore
from app.config import settings

schema = strawberry.Schema(query=Query, mutation=Mutation, config=StrawberryConfig(auto_camel_case=True))


def create_app():
    app = FastAPI()
    graphql_app = GraphQLRouter(schema, graphiql=True)
    app.include_router(filestore.router, prefix="/"+settings.HTTP_FILE_DL_ENDPOINT)
    app.include_router(graphql_app, prefix="/graphql")
    return app
