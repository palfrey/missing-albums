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
import musicbrainz2.webservice as ws
import musicbrainz2.model as m

import sqlite3
from os import walk
from os.path import splitext,join, abspath
import sys

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
				except IOError:
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
#print artists
print sorted(artists.keys())

logging.basicConfig()
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def getAlbums(artist):
	q = ws.Query()

	f = ws.ArtistFilter(name=artist, limit=5)
	artistResults = q.getArtists(f)

	assert artistResults[0].artist.name == artist, (artistResults[0].artist.name,artist)
	artist_id = artistResults[0].artist.id

	try:
		# The result should include all official albums.
		#
		inc = ws.ArtistIncludes(
			releases=(m.Release.TYPE_OFFICIAL, m.Release.TYPE_ALBUM),
			tags=True, releaseGroups=True)
		artist = q.getArtistById(artist_id, inc)
	except ws.WebServiceError, e:
		raise

	if len(artist.getReleases()) == 0:
		raise Exception, "No releases found for %s"%artist

	ret = {}
	for release in artist.getReleases():
		inc = ws.ReleaseIncludes(artist=True, releaseEvents=True, labels=True,
		discs=True, tracks=True, releaseGroup=True)
		release = q.getReleaseById(release.id, inc)
		ret[release.title] = {"when":release.getEarliestReleaseDate(), "ASIN":release.asin}
	return ret

for artist in artists.keys():
	print "artist",artist
	albums = getAlbums(artist)
	print artist, albums
	break

