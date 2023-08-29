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

import app.dependencies
from app.config import settings
import asyncio
import uvicorn
from app.db.session import engine
from app.app import create_app


application = create_app()

if __name__ == "__main__":
    app.dependencies.check_tmp_dir()
    print("Starting uvicorn server...")
    uvicorn.run("main:application", host="0.0.0.0", port=settings.HTTP_PORT, reload=False)
#                log_level=settings.APP_LOG_LEVEL, log_config='logging.yaml')

