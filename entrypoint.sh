#!/bin/bash
# vfeeg-filestor file handling for eegFaktura
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
#+

PYTHON=`which python3`

#if DB_PASSWORD EVN var ist not set
if [ "$DB_PASSWORD" == "" ]; then
  #check if DB_PASSWORD_FILE var is set
  if [ "$DB_PASSWORD_FILE" != "" ]; then
    #check if file exists
    if [ -e "$DB_PASSWORD_FILE" ]; then
      DB_PASSWORD=`cat "$DB_PASSWORD_FILE"`
    fi
  fi
fi

# Space for extra tasks
# Initialize DB
alembic upgrade head
# Run main.py
$PYTHON main.py
