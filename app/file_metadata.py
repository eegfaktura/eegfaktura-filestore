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

from app.rest.models.file_model import FileCategoryEnum

# File categories are global (shared by all tenants), so a category name must never come
# freely from a client. Only these may be used (same list as the REST enum); a missing row
# for one of them is created on first use.
allowed_file_categories = [c.value for c in FileCategoryEnum]

allowed_media_types = [
    'application/pdf',
    'image/jpeg',
    'image/png',
]

