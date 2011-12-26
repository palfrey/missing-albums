#!/bin/sh

echo "drop table amazon;" | sqlite3 songs.db
echo "drop table musicbrainz;" | sqlite3 songs.db
zcat dump.sql.gz | sqlite3 songs.db
