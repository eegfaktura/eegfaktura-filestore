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


import errno
import os.path
import re
import time

import aiofiles
import shutil
import urllib

import uuid
from datetime import datetime

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import subqueryload
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.config import settings
from app.models import file_model, file_container_model, storage_model

from fastapi import Request


def convert_camel_case(name):
    pattern = re.compile(r'(?<!^)(?=[A-Z])')
    name = pattern.sub('_', name).lower()
    return name


def get_only_selected_fields(db_baseclass_name, info):
    db_relations_fields = inspect(db_baseclass_name).relationships.keys()
    selected_fields = [convert_camel_case(field.name) for field in
                       info.selected_fields[0].selections if field.name not in db_relations_fields]
    return selected_fields


def get_valid_data(model_data_object, model_class):
    data_dict = {}

    for column in model_class.__table__.columns:
        try:
            data_dict[column.name] = getattr(model_data_object, column.name)
        except:
            pass

    return data_dict


def get_file_download_uri(file_id: uuid.UUID, caching: bool = False):
    return f"{settings.HTTP_FILE_DL_BASE_URI}/{file_id}" \
           f"{'' if caching == True else '?' + str(time.time())}"


async def get_file_download_metadata(file_id: uuid.UUID):
    """
    Get all required infos for a file by id
    :param file_id: File id to get file info for
    :return: dict containing
    """

    if is_valid_uuid(file_id):

        async with get_session() as s:
            filequery = select(file_model.File) \
                .options(selectinload(file_model.File.file_attributes)) \
                .filter(file_model.File.id == file_id) \
                .order_by(file_model.File.created_at)

            file = (await s.execute(filequery)).scalar()

            if file is not None:

                file_metadata_dict = {
                    "name": file.name,
                    "file_id": file.id,
                    "file_attributes": {att.key: att.value for att in file.file_attributes}
                }

                file_container_query = select(file_container_model.FileContainer) \
                    .filter(file_container_model.FileContainer.id == file.file_container_id)

                file_container = (await s.execute(file_container_query)).scalar()

                if file_container is not None:

                    file_metadata_dict["file_container_id"] = file_container.id
                    file_metadata_dict["file_container_configuration"] = file_container.configuration

                    storage_query = select(storage_model.Storage) \
                        .filter(storage_model.Storage.id == file_container.storage_id)

                    storage = (await s.execute(storage_query)).scalar()

                    if storage is not None:
                        file_metadata_dict["storage_id"] = storage.id
                        file_metadata_dict["storage_configuration"] = storage.configuration

                    else:
                        file_metadata_dict["storage_id"] = None

                else:
                    file_metadata_dict["file_container_id"] = None

            else:
                file_metadata_dict = {}
    else:
        file_metadata_dict = {}

    return file_metadata_dict


def is_valid_uuid(value):
    try:
        uuid.UUID(str(value))
        return True

    except ValueError:
        return False


async def calculate_file_attributes(filename: str):
    file_attributes_dict = {}

    if not os.path.isfile(filename):
        raise FileNotFoundError(
            errno.ENONET, os.strerror(errno.ENONET), filename
        )

    return file_attributes_dict


async def upload_file(source_file_object: UploadFile, target_file_name: str):
    path = os.path.split(target_file_name)[0]

    if not os.path.isdir(path):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), path
        )

    async with aiofiles.open(target_file_name, "wb") as target_file:
        content = await source_file_object.read()
        await target_file.write(content)


def delete_file(file_name: str):
    if not os.path.isfile(file_name):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), file_name
        )

    os.remove(file_name)

0
def move_file(file_source_name: str, file_target_name: str, overwrite: bool = True):

    target_path = os.path.dirname(file_target_name)

    if not os.path.isfile(file_source_name):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), file_source_name
        )

    if not overwrite and os.path.isfile(file_target_name):
        raise FileExistsError(
            errno.EEXIST, os.strerror(errno.EEXIST), file_target_name
        )

    if not os.path.isdir(target_path):
        #TODO Logging
        os.makedirs(target_path, 0o660)

    shutil.move(file_source_name, file_target_name)


def check_tmp_dir():
    if not os.path.isdir(settings.FILESTORE_TEMP_DIR):
        # TODO Log file creation
        os.mkdir(settings.FILESTORE_TEMP_DIR, mode=0o660)

def get_absolute_url(url: str, request: Request):
    # test if is absolute URL
    if urllib.parse.urlparse(url).scheme != "":
        # if 0.0.0.0 is in url (placeholder for replacing with current hostname)
        if "://0.0.0.0" in url:
            return url.replace("://0.0.0.0", f"://{request.url.hostname}")

        return url

    else:
        return f"{request.url.scheme}://{request.url.hostname}"

