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

import os.path
import uuid

from datetime import datetime

from app.file_metadata import allowed_media_types
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import subqueryload, load_only, selectinload

from app.config import settings

from app.db.session import get_session
from app.dependencies import get_valid_data, get_file_download_uri, upload_file, delete_file, move_file
from app.models import file_container_model, file_category_model, file_model, file_attribute_model, storage_model
from app.graphql.scalars.file_scalar import File, FileCategoryWrong, NoFileContainerFound, AddFile, AddFileError


async def get_files(community_id: str, info, limit:int):
    """
    Get all files for community
    :param community_id: Community id to search for files
    :param info:
    :param limit: limit the amount of returned elements
    :return: Commmunity file list
    """
    async with get_session() as s:

        filequery = select(file_model.File) \
            .options(load_only(file_model.File.community_id,
                               file_model.File.user_id,
                               file_model.File.created_at,
                               file_model.File.name),
                     selectinload(file_model.File.file_container)
                     .selectinload(file_container_model.FileContainer.file_category)
                     .options(load_only(file_category_model.FileCategory.name)),
                     selectinload(file_model.File.file_attributes)
                     .options(load_only(file_attribute_model.FileAttribute.key,
                                        file_attribute_model.FileAttribute.value)))\
            .filter(file_model.File.community_id == community_id).order_by(file_model.File.created_at.desc()).limit(limit)

        db_files = (await s.execute(filequery)).scalars()

    file_dicts = []
    for file in db_files:
        file_dict = get_valid_data(file, file_model.File)
        file_dict["attributes"] = file.file_attributes
        file_dict["file_category"] = file.file_container.file_category.name
        file_dict["file_download_uri"] = f"{settings.HTTP_FILE_DL_BASE_URI}/{file.id}"
        file_dicts.append(File(**file_dict))

    return file_dicts


async def get_file(id: uuid.UUID, info):
    """
    Get file specified by id
    :param id: File uuid
    :param info:
    :return: Specified file
    """
    async with get_session() as s:
        filequery = select(file_model.File) \
            .options(load_only(file_model.File.community_id,
                               file_model.File.user_id,
                               file_model.File.created_at,
                               file_model.File.name),
                     selectinload(file_model.File.file_container)
                     .selectinload(file_container_model.FileContainer.file_category)
                     .options(load_only(file_category_model.FileCategory.name)),
                     selectinload(file_model.File.file_attributes)
                     .options(load_only(file_attribute_model.FileAttribute.key,
                                        file_attribute_model.FileAttribute.value)))\
            .filter(file_model.File.id == id)

        file = (await s.execute(filequery)).scalars().unique().one()

    if file is None:
        raise Exception("Cant't find file")

    file_dict = get_valid_data(file, file_model.File)
    file_dict["attributes"] = file.file_attributes
    file_dict["file_category"] = file.file_container.file_category.name
    file_dict["file_download_uri"] = f"{settings.HTTP_FILE_DL_BASE_URI}/{file.id}"


    return File(**file_dict)


async def add_file(file: UploadFile, name: str, file_category: str, community_id: str, user_id: uuid.UUID = None):
    """
    Add File
    """
    try:
        # first check if filetype is allowed to upload
        if file.content_type not in allowed_media_types:
            return AddFileError(message="Invalid content_type")

        async with get_session() as s:
            sql_file_category = select(file_category_model.FileCategory).filter(file_category_model.FileCategory.name == file_category)
            db_file_category = (await s.execute(sql_file_category)).scalars().first()

            if db_file_category is None:
                if settings.FILESTORE_CREATE_UNKNOWN_CATEGORY:
                    db_file_category = file_category_model.FileCategory(name=file_category)
                    s.add(db_file_category)
                    await s.flush()
                else:
                    return AddFileError(message="Invalid file category")

            file_category_id = db_file_category.id

            sql_file_container = select(file_container_model.FileContainer).options(
                selectinload(file_container_model.FileContainer.storage)) \
                .filter(file_category_id == file_container_model.FileContainer.file_category_id) \
                .filter(community_id == file_container_model.FileContainer.community_id)
            db_file_container = (await s.execute(sql_file_container)).scalars().first()

            if db_file_container is not None:
                db_storage = db_file_container.storage
            else:
                db_storage = None

            if db_storage is None:
                if settings.FILESTORE_CREATE_UNKNOWN_STORAGE:
                    # create container
                    db_storage = storage_model.Storage(name=f"Community {community_id} default storage", community_id=community_id)
                    s.add(db_storage)
                    await s.flush()

                else:
                    # Return Error if requested storage does not exist and auto-creation is disabled
                    return AddFileError(message="No storage for community found")

            str_storage_id = str(db_storage.id)

            if db_file_container is None:
                if settings.FILESTORE_CREATE_UNKNOWN_CONTAINER:
                    db_file_container = file_container_model.FileContainer(
                        name=f"Community {community_id} default {file_category} container", community_id=community_id, file_category=db_file_category,
                        storage=db_storage)
                    s.add(db_file_container)
                    await s.flush()

                else:
                    # Return Error Type if requested container does not exist and auto-creation is disabled
                    return AddFileError(message="No file Container found")

            str_container_id = str(db_file_container.id)

            # TODO Add file Management ...

            db_file = file_model.File(community_id=community_id,
                                       user_id=user_id,
                                       name=name,
                                       file_container=db_file_container)

            s.add(db_file)
            await s.flush()


            tmpfilename = f"{settings.FILESTORE_TEMP_DIR}/{str(db_file.id)}"
            await upload_file(file, tmpfilename)

            s.add(file_attribute_model.FileAttribute(file=db_file, key="orig_file_name", value=os.path.splitext(file.filename)[0]))
            s.add(file_attribute_model.FileAttribute(file=db_file, key="file_extension", value=os.path.splitext(file.filename)[1][1:]))
            s.add(file_attribute_model.FileAttribute(file=db_file, key="media_type", value=file.content_type))


            targetfile = f"{settings.FILESTORE_LOCAL_BASE_DIR}/{str_storage_id}/{str_container_id}/{str(db_file.id)}"
            move_file(tmpfilename, targetfile)

            s.add(file_attribute_model.FileAttribute(file=db_file, key="file_bytes", value=str(os.path.getsize(targetfile))))

            await s.commit()

        #TODO File Metadata handling ;) ;) ;)

        file_dict = db_file.as_dict()
        file_dict["file_category"] = file_category
        file_dict["file_download_uri"] = get_file_download_uri(file_dict["id"])

        del file_dict["file_container_id"]
        del file_dict["community_id"]

        return AddFile(**file_dict)

    except FileNotFoundError as fnfe:
        #TODO Log error
        return AddFileError(message=f"{fnfe.strerror}  {fnfe.filename}")


async def add_invoice(file: UploadFile, name: str, community_id: str, user_id: uuid.UUID):
    return add_file(file, name, "invoice", community_id, user_id)

async def get_invoices(community_id: str, user_id: uuid.UUID, info, limit:int):
    """
    Get Invoices for user_id
    :param info: Info
    :param community_id: Community id to search for user invoices
    :param user_id: User id to search invoices for
    :param limit: limit the amount of returned elements
    :return: Invoices list
    """
    async with get_session() as s:

        filequery = select(file_model.File) \
            .options(load_only(file_model.File.community_id,
                               file_model.File.user_id,
                               file_model.File.created_at,
                               file_model.File.name),
                     selectinload(file_model.File.file_container)
                     .selectinload(file_container_model.FileContainer.file_category)
                     .options(load_only(file_category_model.FileCategory.name)),
                     selectinload(file_model.File.file_attributes)
                     .options(load_only(file_attribute_model.FileAttribute.key,
                                        file_attribute_model.FileAttribute.value))) \
            .filter(file_model.File.community_id == community_id) \
            .filter(file_model.File.user_id == user_id) \
            .filter(file_category_model.FileCategory.name == "invoice").order_by(file_model.File.created_at.desc()).limit(limit)

        db_files = (await s.execute(filequery)).scalars()

    file_dicts = []
    for file in db_files:
        file_dict = get_valid_data(file, file_model.File)
        file_dict["attributes"] = file.file_attributes
        file_dict["file_category"] = file.file_container.file_category.name
        file_dict["file_download_uri"] = f"{settings.HTTP_FILE_DL_BASE_URI}/{file.id}"
        file_dicts.append(File(**file_dict))

    return file_dicts


async def get_invoice(id: uuid.UUID, info):
    """
    Get file specified by id
    :param id: File uuid
    :param info:
    :return: Specified file
    """
    async with get_session() as s:
        filequery = select(file_model.File) \
            .options(load_only(file_model.File.community_id,
                               file_model.File.user_id,
                               file_model.File.created_at,
                               file_model.File.name),
                     selectinload(file_model.File.file_container)
                     .selectinload(file_container_model.FileContainer.file_category)
                     .options(load_only(file_category_model.FileCategory.name)),
                     selectinload(file_model.File.file_attributes)
                     .options(load_only(file_attribute_model.FileAttribute.key,
                                        file_attribute_model.FileAttribute.value)))\
            .filter(file_model.File.id == id) \
            .filter(file_category_model.FileCategory.name == "invoice")

        file = (await s.execute(filequery)).scalars().unique().one()

    if file is None:
        raise Exception("Cant't find file")

    file_dict = get_valid_data(file, file_model.File)
    file_dict["attributes"] = file.file_attributes
    file_dict["file_category"] = file.file_container.file_category.name
    file_dict["file_download_uri"] = f"{settings.HTTP_FILE_DL_BASE_URI}/{file.id}"

    return File(**file_dict)
