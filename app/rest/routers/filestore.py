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
import urllib

import uuid

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from starlette.responses import JSONResponse

from app.config import settings
from app.db.session import get_session
from app.dependencies import get_file_download_metadata, upload_file, move_file, get_file_download_uri
from app.file_metadata import allowed_media_types
from app.models import file_category_model, file_container_model, storage_model, file_model, file_attribute_model

from app.rest.models.default import ErrorMessage
from app.rest.models.file_model import FileCategoryEnum, FileUploadResponse

router = APIRouter()


@router.get(
    "/",
    response_model=ErrorMessage,
    responses={
        400: {"model": ErrorMessage, "description": "Error Message"}
    }
)
async def endoint_without_parameters():
    return JSONResponse(status_code=400, content={"detail": "No parameter given"})


@router.get(
    "/{file_id}",
    response_class=FileResponse,
    responses={
        404: {"model": ErrorMessage, "desctiption": "File not found error message"},
        200: {
            "description": "File download",
            "content": {content_type: {"schema":{"type": "string", "format": "binary"}} for content_type in
                        allowed_media_types}
        }
    }
)
async def download_file(file_id: uuid.UUID):
    metadata = await get_file_download_metadata(file_id)

    # Test if file entry was found
    if not metadata:
        # TODO Logging
        raise HTTPException(status_code=404, detail="File not found 1")

    # Test if file container is present
    if "file_container_id" not in metadata or \
            metadata["file_container_id"] is None:
        # TODO Logging
        raise HTTPException(status_code=404, detail="File not found 2")

    # Test if file container is present
    if "storage_id" not in metadata or \
            metadata["storage_id"] is None:
        # TODO Logging
        raise HTTPException(status_code=404, detail="File not found 3")

    # Test if file extension is present
    if "file_attributes" not in metadata or \
            metadata["file_attributes"] is None or \
            "file_extension" not in metadata["file_attributes"] or \
            metadata["file_attributes"]["file_extension"] is None:
        # TODO Logging
        raise HTTPException(status_code=404, detail="File not found 4")

    # TODO Check Rights to download file

    if not os.path.isdir(settings.FILESTORE_LOCAL_BASE_DIR):
        # TODO Logging
        raise HTTPException(status_code=404, detail="File not found 5")

    if not os.path.isdir(settings.FILESTORE_LOCAL_BASE_DIR + "/" + str(metadata["storage_id"])):
        # TODO Logging
        raise HTTPException(status_code=404, detail="File not found 6")

    if not os.path.isdir(settings.FILESTORE_LOCAL_BASE_DIR + "/" + str(metadata["storage_id"]) + "/" + str(
            metadata["file_container_id"])):
        # TODO Logging
        raise HTTPException(status_code=404, detail="File not found 7")

    if not os.path.isfile(
            settings.FILESTORE_LOCAL_BASE_DIR + "/" + str(metadata["storage_id"]) + "/" + str(
                metadata["file_container_id"]) + "/" + str(file_id)):
        # TODO Logging
        print(settings.FILESTORE_LOCAL_BASE_DIR + "/" + str(metadata["storage_id"]) + "/" + str(
            metadata["file_container_id"]) + "/" + str(file_id))
        raise HTTPException(status_code=404, detail="File not found 8")

    return FileResponse(
        settings.FILESTORE_LOCAL_BASE_DIR + "/" + str(metadata["storage_id"]) + "/" + str(
            metadata["file_container_id"]) + "/" + str(file_id),
        media_type=metadata["file_attributes"]["media_type"],
        filename=urllib.parse.quote(metadata["name"] + "." + metadata["file_attributes"]["file_extension"]),
    )


@router.post(
    "/upload/{file_category}/{tenant}/{user_id}",
    response_model=FileUploadResponse,
    responses={
        400: {"model": ErrorMessage, "description": "Issues during file creation"},
        200: {
            "description": "User document upload",
            "content": {
                "application/json": {
                    "example": {
                        "id": "01234567-89ab-cdef-dead-beef01234567",
                        "name": "Hugo",
                        "created_at": "2023-05-09T10:54:40.219113",
                        "file_category": "invoice",
                        "file_download_uri": "http://192.168.108.13:5000/filestore/01234567-89ab-cdef-dead-beef01234567?2023-05-09 10:54:40.258317"
                    }
                }
            }
        }
    }
)
async def add_user_file(file: UploadFile, file_category: FileCategoryEnum, tenant: str,
                        user_id: uuid.UUID) -> FileUploadResponse:
    """ Add file """
    # TODO name determination
    try:
        # first check if filetype is allowed to upload
        if file.content_type not in allowed_media_types:
            raise HTTPException(status_code=400, detail="Invalid content_type")

        name = os.path.splitext(file.filename)[0]

        async with get_session() as s:
            sql_file_category = select(file_category_model.FileCategory).filter(
                file_category_model.FileCategory.name == file_category)
            db_file_category = (await s.execute(sql_file_category)).scalars().first()

            if db_file_category is None:
                if settings.FILESTORE_CREATE_UNKNOWN_CATEGORY:
                    db_file_category = file_category_model.FileCategory(name=file_category)
                    s.add(db_file_category)
                    await s.flush()
                else:
                    raise HTTPException(status_code=400, detail="Invalid file category")

            file_category_id = db_file_category.id

            sql_file_container = select(file_container_model.FileContainer).options(
                selectinload(file_container_model.FileContainer.storage)) \
                .filter(file_category_id == file_container_model.FileContainer.file_category_id) \
                .filter(tenant == file_container_model.FileContainer.tenant)
            db_file_container = (await s.execute(sql_file_container)).scalars().first()

            if db_file_container is not None:
                db_storage = db_file_container.storage
            else:
                db_storage = None

            if db_storage is None:
                if settings.FILESTORE_CREATE_UNKNOWN_STORAGE:
                    # create container
                    db_storage = storage_model.Storage(name=f"Community {tenant} default storage",
                                                       tenant=tenant)
                    s.add(db_storage)
                    await s.flush()

                else:
                    # Return Error if requested storage does not exist and auto-creation is disabled
                    raise HTTPException(status_code=400, detail="No storage for community found")

            str_storage_id = str(db_storage.id)

            if db_file_container is None:
                if settings.FILESTORE_CREATE_UNKNOWN_CONTAINER:
                    db_file_container = file_container_model.FileContainer(
                        name=f"Community {tenant} default {file_category} container", tenant=tenant,
                        file_category=db_file_category,
                        storage=db_storage)
                    s.add(db_file_container)
                    await s.flush()

                else:
                    # Return Error Type if requested container does not exist and auto-creation is disabled
                    raise HTTPException(status_code=400, detail="No file Container found")

            str_container_id = str(db_file_container.id)

            # TODO Add file Management ...

            db_file = file_model.File(tenant=tenant,
                                      user_id=user_id,
                                      name=name,
                                      file_container=db_file_container)

            s.add(db_file)
            await s.flush()

            tmpfilename = f"{settings.FILESTORE_TEMP_DIR}/{str(db_file.id)}"
            await upload_file(file, tmpfilename)

            s.add(file_attribute_model.FileAttribute(file=db_file, key="orig_file_name",
                                                     value=os.path.splitext(file.filename)[0]))
            s.add(file_attribute_model.FileAttribute(file=db_file, key="file_extension",
                                                     value=os.path.splitext(file.filename)[1][1:]))
            s.add(file_attribute_model.FileAttribute(file=db_file, key="media_type", value=file.content_type))

            targetfile = f"{settings.FILESTORE_LOCAL_BASE_DIR}/{str_storage_id}/{str_container_id}/{str(db_file.id)}"
            move_file(tmpfilename, targetfile)

            s.add(file_attribute_model.FileAttribute(file=db_file, key="file_bytes",
                                                     value=str(os.path.getsize(targetfile))))

            await s.commit()

        file_dict = db_file.as_dict()
        file_dict["file_category"] = file_category
        file_dict["file_download_uri"] = get_file_download_uri(file_dict["id"])

        del file_dict["file_container_id"]
        del file_dict["community_id"]

        return FileUploadResponse(**file_dict)

    except FileNotFoundError as fnfe:
        # TODO Log error
        raise HTTPException(status_code=400, detail=f"{fnfe.strerror} {fnfe.filename}")


#@router.post("/upload/{file_category}/{tenant}")
#async def add_community_file(self, file: UploadFile, file_category: FileCategoryEnum, tenant: str):
#    """ Add file """
#
#    # TODO upload function for communtiy global files
