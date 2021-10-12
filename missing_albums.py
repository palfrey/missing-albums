import pathlib
from mutagen import File
from mutagen.asf import ASF, ASFTags
from mutagen.apev2 import APEv2File
from mutagen.flac import FLAC
from mutagen.id3 import ID3FileType
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.oggflac import OggFLAC
from mutagen.oggspeex import OggSpeex
from mutagen.oggtheora import OggTheora
from mutagen.oggvorbis import OggVorbis
from mutagen.trueaudio import TrueAudio
from mutagen.wavpack import WavPack
from mutagen.mp4 import MP4, MP4Tags
from mutagen.musepack import Musepack
from mutagen.monkeysaudio import MonkeysAudio
from mutagen.optimfrog import OptimFROG

import logging
import musicbrainzngs

import sqlite3
from os import walk
from os.path import join, abspath
import sys
from time import sleep, strftime, strptime, struct_time, localtime
import math
import codecs

import jinja2
from os import mkdir
from os.path import exists

from optparse import OptionParser
from configparser import ConfigParser

import requests

musicbrainzngs.set_useragent("Missing Albums", "0.1")

parser = OptionParser()
parser.add_option(
    "-m",
    "--music-dir",
    dest="directory",
    default=".",
    help="Pick music files directory. Default is current directory",
)
parser.add_option(
    "-d", "--database", dest="db", default="songs.db", help="Songs database file"
)
parser.add_option(
    "--overrides", dest="overrides", default=None, help="Overrides info file"
)
parser.add_option(
    "--no-walk",
    dest="walk",
    default="True",
    action="store_false",
    help="Don't re-read music directory",
)
parser.add_option(
    "--artists-only",
    dest="artistsOnly",
    default=False,
    action="store_true",
    help="Write out simplified artists list",
)
(opts, args) = parser.parse_args()

overrides = {"artist": {}, "ignore": {}}

if opts.overrides is not None:
    cp = ConfigParser()
    cp.read([opts.overrides])
    for section in cp.sections():
        if section == "artist":
            overrides["artist"] = dict(cp.items(section))
        elif section == "ignore":
            overrides["ignore"] = cp.options(section)
        else:
            raise Exception(section)


class EasyMP3(MP3):
    def __init__(self, *args, **kwargs):
        kwargs["ID3"] = EasyID3
        MP3.__init__(self, *args, **kwargs)


class EasierTags:
    def __getitem__(self, key):
        if key in list(self.simpler.keys()):
            return self._parent.__getitem__(self, self.simpler[key])
        else:
            return self._parent.__getitem__(self, key)


class EasyMP4Tags(MP4Tags, EasierTags):
    simpler = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb"}


class EasyMP4(MP4):
    def load(self, filename):
        MP4.load(self, filename)
        self.tags.__class__ = EasyMP4Tags


class EasyASFTags(EasierTags, ASFTags):
    _parent = ASFTags
    simpler = {"title": "Title"}


class EasyASF(ASF):
    def load(self, filename):
        ASF.load(self, filename)
        self.tags.__class__ = EasyASFTags


options = [
    EasyMP3,
    TrueAudio,
    OggTheora,
    OggSpeex,
    OggVorbis,
    OggFLAC,
    FLAC,
    APEv2File,
    EasyMP4,
    ID3FileType,
    WavPack,
    Musepack,
    MonkeysAudio,
    OptimFROG,
    EasyASF,
]

covers_folder = pathlib.Path(__file__).parent.joinpath("covers")

doregen = True
con = sqlite3.connect(opts.db)
cur = con.cursor()
cur.execute("select name from sqlite_master where type='table' and name='songs'")
if len(cur.fetchall()) == 0:
    cur.execute(
        "create table songs (fullpath text(300) primary key, artist text(100),album text(100),title text(100),duration integer);"
    )
    con.commit()

if opts.walk:
    for path, dirs, files in walk(opts.directory):
        for f in files:
            if f[0] == ".":
                continue  # ignore hidden files
            try:
                fp = abspath(join(path, f))
            except UnicodeDecodeError:
                print(type(join(path, f)), path, f)
                raise
            cur.execute(
                "select artist,album,title,duration from songs where fullpath=?", (fp,)
            )
            d = cur.fetchall()
            if d == []:
                try:
                    data = File(fp, options=options)
                except IOError as e:
                    print(e)
                    print("rebuilding song db")
                    data = None
                if data is None:
                    cur.execute(
                        "insert into songs (fullpath,duration) values(?,?)", (fp, -1)
                    )
                    con.commit()
                    continue
                try:
                    try:
                        artist = data["artist"][0].strip()
                    except KeyError:
                        artist = str("")
                    try:
                        album = data["album"][0].strip()
                    except KeyError:
                        album = str("")
                    try:
                        title = data["title"][0].strip()
                    except KeyError:
                        title = str("")
                    duration = int(data.info.length)
                    print((fp, artist, album, title, duration))
                    cur.execute(
                        "insert into songs values(?,?,?,?,?)",
                        (fp, artist, album, title, duration),
                    )
                    con.commit()
                except KeyError:
                    print(fp, list(data.keys()))
                    raise

cur.execute(
    'select artist,album, count(title) from songs group by artist,album having count(title)>2 and artist!=""'
)
artists = {}
lower = {}
d = cur.fetchall()
# print d
for (artist, album, title) in d:
    if artist.lower() in lower:
        artist = lower[artist.lower()]
    if artist not in artists:
        artists[artist] = {}
        lower[artist.lower()] = artist
    artists[artist][album] = title

# print artists.keys()

logging.basicConfig()
logger = logging.getLogger()
# logger.setLevel(logging.DEBUG)


def getAlbums(artist):
    cur.execute(
        "select album, asin, date, ep from musicbrainz where artist=?", (artist,)
    )
    d = cur.fetchall()
    if d == []:
        while True:
            try:
                artistResults = musicbrainzngs.search_artists(query=artist, limit=5)
                break
            except BaseException as e:
                print("problem during artist name", e)
                sleep(5)

        ret = {}
        for artistResult in artistResults["artist-list"]:
            print(artistResult)
            print("name", artistResult["name"])
            artist_id = artistResult["id"]

            release_ids = []

            for kind in ["album", "ep", "soundtrack", "live"]:
                while True:
                    try:
                        # The result should include all official albums.
                        releases = musicbrainzngs.browse_releases(
                            artist=artist_id,
                            release_status=["official"],
                            release_type=kind,
                        )
                        release_ids.extend(
                            [
                                (release["id"], kind)
                                for release in releases["release-list"]
                            ]
                        )
                        break
                    except BaseException as e:
                        raise
                        print("problem during releases", e)
                        sleep(5)

            if release_ids == []:
                print("No releases found for %s" % artist)
                continue

            print("release ids", release_ids)

            ret = {}
            lower = {}
            for (id, kind) in release_ids:
                while True:
                    try:
                        release = musicbrainzngs.get_release_by_id(
                            id, includes=["release-rels", "release-groups"]
                        )["release"]
                        break
                    except BaseException as e:
                        print("problem during release", e)
                        sleep(5)
                print(release)
                if release.get("asin") is None:  # ignore these
                    print("skipping because no ASIN:", id, release["title"])
                    continue
                title = release["title"]
                if title.find("(disc ") != -1:
                    title = title[: title.find("(disc ")].strip()

                # assert title not in ret.keys(),(title, release)
                if title.lower() in lower:
                    title = lower[title.lower()]
                else:
                    lower[title.lower()] = title

                if "release-event-list" not in release:
                    print(
                        "skipping because no release event list", id, release["title"]
                    )
                    continue

                if "date" not in release["release-event-list"][0]:
                    print("skipping because no release date", id, release["title"])
                    continue

                ret[title] = {
                    "when": release["release-event-list"][0]["date"],
                    "asin": release["asin"],
                    "ep": kind == "ep",
                }
                print("got", title)
                cover_path = covers_folder.joinpath(f"{release['asin']}.jpg")
                if not cover_path.exists():
                    try:
                        cover_art = musicbrainzngs.get_image_front(id)
                        cover_path.open("wb").write(cover_art)
                    except musicbrainzngs.ResponseError as e:
                        if e.cause.code != 404:
                            print("error getting cover art", release, e.cause)
                            raise

                if not cover_path.exists():
                    # Main release failed, let's try release group
                    release_group_id = release["release-group"]["id"]
                    try:
                        cover_art = musicbrainzngs.get_release_group_image_front(
                            release_group_id
                        )
                        cover_path.open("wb").write(cover_art)
                    except musicbrainzngs.ResponseError as e:
                        if e.cause.code != 404:
                            print("error getting cover art", release, e.cause)
                            raise

            if ret == {}:
                print("no usable releases")
                continue
            else:
                break

        if ret == {}:
            raise Exception(
                "No usable albums/artists found for %s. Try fixing one of the entries marked 'skipping because no ASIN', or add to the ignore list"
                % artist
            )
        for title in ret:
            cur.execute(
                "insert into musicbrainz values(?, ?, ?, ?, ?)",
                (
                    artist,
                    title,
                    ret[title]["asin"],
                    ret[title]["when"],
                    ret[title]["ep"],
                ),
            )
        con.commit()
    else:
        ret = {}
        lower = {}
        for (album, asin, when, ep) in d:
            if album.lower() in lower:
                album = lower[album.lower()]
            else:
                lower[album.lower()] = album
            ret[album] = {"asin": asin, "when": when, "ep": ep}

    keys = list(ret.keys())

    for title in keys:
        if title.find("(") != -1:
            stripped = title[: title.find("(")].strip()
            if len(stripped) > 0 and stripped[-1] == ".":
                stripped = stripped[:-1]
            if stripped in list(ret.keys()):
                print("removed", title, stripped)
                del ret[title]
                continue

        try:
            ret[title]["when"] = strptime(ret[title]["when"], "%Y-%m-%d")
        except ValueError:
            if ret[title]["when"].find("-") != -1:
                ret[title]["when"] = struct_time(
                    (
                        int(ret[title]["when"][: ret[title]["when"].find("-")]),
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                        0,
                    )
                )
            else:
                ret[title]["when"] = struct_time(
                    (int(ret[title]["when"]), 0, 0, 0, 0, 0, 0, 0, 0)
                )
        except TypeError:
            if type(ret[title]["when"]) == int:
                ret[title]["when"] = struct_time(
                    (ret[title]["when"], 0, 0, 0, 0, 0, 0, 0, 0)
                )
            elif ret[title]["when"] is None:
                pass
            else:
                raise
    return ret


most_tracks = [
    x
    for x in sorted(list(artists.keys()), key=lambda x: sum(artists[x].values()))
    if sum(artists[x].values()) > 3
]
print(most_tracks)

cur.execute("select name from sqlite_master where type='table' and name='musicbrainz'")
if len(cur.fetchall()) == 0:
    cur.execute(
        "create table musicbrainz (artist text(100), album text(100), asin text(20), date integer, ep boolean, primary key(artist, album));"
    )
    con.commit()

cur.execute("select name from sqlite_master where type='table' and name='amazon'")
if len(cur.fetchall()) == 0:
    cur.execute(
        "create table amazon (artist text(100), album text(100), url text(500), image text(500), amazon_new integer, primary key(artist, album));"
    )
    con.commit()


def compact(inp):
    inp = inp.lower()
    return (
        inp.replace("'", "")
        .replace(",", " ")
        .replace("&", " ")
        .replace(":", " ")
        .replace(".", " ")
    )


missing = {}

for artist in most_tracks:
    if artist.lower() in overrides["artist"]:
        newartist = overrides["artist"][artist.lower()]
        artists[newartist] = artists[artist]
        del artists[artist]
        artist = newartist

    if artist.lower() in overrides["ignore"]:
        continue

    print("artist", artist, type(artist), artist.encode("utf-8"))
    albums = getAlbums(artist)
    print(artist, list(albums.keys()), artists[artist])

    newest = None
    for got_a in list(artists[artist].keys()):
        use_a = None
        if got_a in list(albums.keys()):
            use_a = got_a
        else:
            items = [x for x in compact(got_a).split() if x not in ("(ep)",)]
            for k in list(albums.keys()):
                for i in items:
                    if i not in compact(k):
                        break
                else:
                    # print "found all bits", items, k
                    use_a = k
                    break
        if use_a is not None:
            if newest is None or newest < albums[use_a]["when"]:
                newest = albums[use_a]["when"]
        else:
            print("Can't find '%s'" % got_a, list(albums.keys()))

    for a in list(albums.keys()):
        album = albums[a]
        if (newest is None or album["when"] > newest) and not album["ep"]:
            print(album)
            results = {
                "title": a,
                "url": f"https://www.amazon.co.uk/dp/{album['asin']}",
                "image": f"covers/{album['asin']}.jpg",
            }
            print("missing", results, album["when"], artist)
            when = albums[a]["when"]
            if when not in missing:
                missing[when] = []
            results["artist"] = artist
            results["when"] = when
            missing[when].append(results)
            # raise Exception,albums[a]
    # break

artists = {}

if opts.artistsOnly:
    for when in sorted(missing, reverse=True):
        for m in missing[when]:
            if m["artist"] not in artists:
                artists[m["artist"]] = []
            artists[m["artist"]].append(m["title"])

    f = codecs.open("artists.txt", "wb", "utf-8")
    for a in sorted(artists):
        f.write("%s - %s\n" % (a, ", ".join(artists[a])))
    f.close()

    sys.exit(0)

folder = "output"

if not exists(folder):
    mkdir(folder)

flattened = []
for key in sorted(missing, reverse=True):
    if key > localtime():  # ignore items not released yet
        continue
    flattened.extend([x for x in missing[key] if x["url"] is not None])
count = len(flattened)
perpage = 10
pages = int(math.ceil(count / (perpage * 1.0)))

print(count, pages)

links = [("1", "index.html")] + [
    (str(x), "index%03d.html" % x) for x in range(2, pages + 1)
]


env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("."), autoescape=jinja2.select_autoescape()
)

nt = env.get_template("template.html")

for start in range(0, count, perpage):
    index = (start / perpage) + 1

    if index == 1:
        name = "index.html"
    else:
        name = "index%03d.html" % index

    print(flattened[start : start + perpage])

    open(join(folder, name), "w").write(
        nt.render(
            albums=flattened[start : start + perpage],
            links=links,
            index=str(index),
            strftime=strftime,
        )
    )
