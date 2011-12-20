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

import amazon

import logging
import musicbrainz2.webservice as ws
import musicbrainz2.model as m

import sqlite3
from os import walk
from os.path import splitext,join, abspath
import sys
from time import sleep, strptime
from types import IntType

from optparse import OptionParser

parser = OptionParser()
parser.add_option("-m","--music-dir",dest="directory",default=".",help="Pick music files directory. Default is current directory")
parser.add_option("-d","--database",dest="db", default="songs.db",help="Songs database file")
parser.add_option("--no-walk",dest="walk",default="True",action="store_false",help="Don't re-read music directory")
(opts,args) = parser.parse_args()

class EasyMP3(MP3):
	def __init__(self, *args, **kwargs):
		kwargs['ID3'] = EasyID3
		MP3.__init__(self,*args, **kwargs)
	
class EasierTags:
	def __getitem__(self, key):
		if key in self.simpler.keys():
			return self._parent.__getitem__(self,self.simpler[key])
		else:
			return self._parent.__getitem__(self, key)

class EasyMP4Tags(MP4Tags, EasierTags):
	simpler = {"title":"\xa9nam","artist":"\xa9ART","album":"\xa9alb"}

class EasyMP4(MP4):
    def load(self, filename):
		MP4.load(self,filename)
		self.tags.__class__ = EasyMP4Tags

class EasyASFTags(EasierTags, ASFTags):
	_parent = ASFTags
	simpler = {"title":"Title"}

class EasyASF(ASF):
    def load(self, filename):
		ASF.load(self,filename)
		self.tags.__class__ = EasyASFTags

options = [EasyMP3, TrueAudio, OggTheora, OggSpeex, OggVorbis, OggFLAC,
		   FLAC, APEv2File, EasyMP4, ID3FileType, WavPack, Musepack,
		   MonkeysAudio, OptimFROG, EasyASF]

doregen = True
con = sqlite3.connect(opts.db)
cur = con.cursor()
cur.execute("select name from sqlite_master where type='table' and name='songs'")
if len(cur.fetchall())==0:
	cur.execute("create table songs (fullpath text(300) primary key, artist text(100),album text(100),title text(100),duration integer);")
	con.commit()

if opts.walk:
	for path, dirs, files in walk(opts.directory):
		for f in files:
			if f[0] == ".":
				continue # ignore hidden files
			try:
				fp = unicode(abspath(join(path,f)),"utf_8","ignore")
			except UnicodeDecodeError:
				print type(join(path,f)),path,f
				raise
			cur.execute("select artist,album,title,duration from songs where fullpath=?", (fp,))
			d = cur.fetchall()
			if d==[]:
				try:
					data = File(fp, options=options)
				except IOError,e:
					print e
					print "rebuilding song db"
					data = None
				if data == None:
					cur.execute("insert into songs (fullpath,duration) values(?,?)",(fp, -1))
					con.commit()
					continue
				try:
					try:
						artist = data["artist"][0].strip()
					except KeyError:
						artist = unicode("")
					try:
						album = data["album"][0].strip()
					except KeyError:
						album = unicode("")
					try:
						title = data["title"][0].strip()
					except KeyError:
						title = unicode("")
					duration = int(data.info.length)
					print (fp, artist, album, title, duration)
					cur.execute("insert into songs values(?,?,?,?,?)",(fp, artist, album, title, duration))
					con.commit()
				except KeyError:
					print fp,data.keys()
					raise

cur.execute("select artist,album, count(title) from songs group by artist,album having count(title)>2 and artist!=\"\"")
artists = {}
d = cur.fetchall()
#print d
for (artist, album,title) in d:
	if artist not in artists:
		artists[artist] = {}
	artists[artist][album] = title
#print artists.keys()

logging.basicConfig()
logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)

def getAlbums(artist):
	cur.execute("select album, asin, date, ep from musicbrainz where artist=?", (artist,))
	d = cur.fetchall()
	if d == []:
		q = ws.Query()

		f = ws.ArtistFilter(name=artist, limit=5)
		while True:
			try:
				artistResults = q.getArtists(f)
				break
			except ws.WebServiceError, e:
				print dir(e),e.msg, e.message
				raise

		#assert artistResults[0].artist.name == artist, (artistResults[0].artist.name,artist)
		print "name", artistResults[0].artist.name
		artist_id = artistResults[0].artist.id

		release_ids = []

		for kind in (m.Release.TYPE_ALBUM, m.Release.TYPE_EP):
			while True:
				try:
					# The result should include all official albums.
					#
					inc = ws.ArtistIncludes(
						releases=(m.Release.TYPE_OFFICIAL, kind),
						tags=True)
					release_ids.extend([(x.id,kind) for x in q.getArtistById(artist_id, inc).getReleases()])
					break
				except ws.WebServiceError, e:
					print dir(e),e.msg, e.message
					sleep(2)

		if release_ids == []:
			print "No releases found for %s"%artist
			return {}

		print "release ids", release_ids

		ret = {}
		for (id,kind) in release_ids:
			inc = ws.ReleaseIncludes(artist=True, releaseEvents=True)
			while True:
				try:
					release = q.getReleaseById(id, inc)
					break
				except ws.WebServiceError, e:
					print e.msg, e.message
					sleep(3)
			if release.asin == None: # ignore these
				continue
			title = release.title
			if title.find("(disc ")!=-1:
				title = title[:title.find("(disc ")].strip()

			#assert title not in ret.keys(),(title, release)
			ret[title] = {"when":release.getEarliestReleaseDate(), "asin":release.asin, "ep": kind == m.Release.TYPE_EP}
			print "got", title

		for title in ret:
			cur.execute("insert into musicbrainz values(?, ?, ?, ?, ?)", (artist, title, ret[title]["asin"], ret[title]["when"], ret[title]["ep"]))
		con.commit()
	else:
		ret = {}
		for (album, asin, when, ep) in d:
			ret[album] = {"asin":asin, "when":when, "ep": ep}

	keys = ret.keys()

	for title in keys:
		if title.find("(")!=-1:
			stripped = title[:title.find("(")].strip()
			if stripped[-1] == ".":
				stripped = stripped[:-1]
			if stripped in ret.keys():
				print "removed", title, stripped
				del ret[title]
				continue

		try:
			ret[title]["when"] = strptime(ret[title]["when"], "%Y-%m-%d")
		except ValueError:
			if ret[title]["when"].find("-")!=-1:
				ret[title]["when"] = int(ret[title]["when"][:ret[title]["when"].find("-")])
			else:
				ret[title]["when"] = int(ret[title]["when"])
		except TypeError:
			if type(ret[title]["when"]) == IntType:
				ret[title]["when"] = (ret[title]["when"], 0,0,0,0,0,0,0,0)
			elif ret[title]["when"] == None:
				pass
			else:
				raise
	return ret

most_tracks = sorted(artists.keys(), lambda x,y:cmp(sum(artists[y].values()), sum(artists[x].values())))
print most_tracks

cur.execute("select name from sqlite_master where type='table' and name='musicbrainz'")
if len(cur.fetchall())==0:
	cur.execute("create table musicbrainz (artist text(100), album text(100), asin text(20), date integer, ep boolean, primary key(artist, album));")
	con.commit()

cur.execute("select name from sqlite_master where type='table' and name='amazon'")
if len(cur.fetchall())==0:
	cur.execute("create table amazon (artist text(100), album text(100), url text(500), image text(500), amazon_new integer, primary key(artist, album));")
	con.commit()

def compact(inp):
	inp = inp.lower()
	return inp.replace("'","")

for artist in most_tracks:
	print "artist",artist
	albums = getAlbums(artist)
	print artist, albums.keys(), artists[artist]

	newest = None
	for got_a in artists[artist].keys():
		use_a = None
		if got_a in albums.keys():
			use_a = got_a
		else:
			items = [x for x in compact(got_a).split() if x not in ("(ep)",)]
			for k in albums.keys():
				for i in items:
					if i not in compact(k):
						break
				else:
					#print "found all bits", items, k
					use_a = k
					break
		if use_a != None:
			if newest == None or newest < albums[use_a]['when']:
				newest = albums[use_a]['when']
		else:
			print "Can't find '%s'"%got_a, albums.keys()

	for a in albums.keys():
		if albums[a]['when'] > newest and not albums[a]['ep']:
			print "don't have",a, albums[a]['asin'], artist
			cur.execute("select url, image, amazon_new from amazon where artist=? and album=?",(artist, a))
			d = cur.fetchall()
			if d == []:
				results = amazon.searchByTitle(artist, a)
				cur.execute("insert into amazon values(?, ?, ?, ?, ?)",(artist, a, unicode(results["url"]), unicode(results["image"]), results["amazon_new"]))
				con.commit()
			else:
				d = d[0]
				results = {"title":a, "url":d[0], "image":d[1], "amazon_new":d[2]}
			print results
			#raise Exception,albums[a]
	#break


