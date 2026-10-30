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

import app.dependencies
from app.config import settings
from app.logging_config import configure_logging
import uvicorn
from app.app import create_app


application = create_app()

if __name__ == "__main__":
    configure_logging()
    app.dependencies.check_tmp_dir()
    logging.getLogger(__name__).info("Starting uvicorn server...")
    # log_config=None: uvicorn keeps the setup above; access_log=False: app.access_log writes the access line
    uvicorn.run("main:application", host="0.0.0.0", port=settings.HTTP_PORT, reload=False,
                log_config=None, access_log=False)

