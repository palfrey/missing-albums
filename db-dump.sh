#!/bin/sh

echo ".dump amazon" | sqlite3 songs.db > dump.sql
echo ".dump musicbrainz" | sqlite3 songs.db >> dump.sql
gzip -f dump.sql
