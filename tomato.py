# -*- coding: utf-8 -*-

import sys

import cgi
import os
import datetime
import pickle
from google.appengine.ext.webapp import template
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
#from google.appengine.ext import db
from google.appengine.api import urlfetch
from google.appengine.api import memcache
import feedparser
import dateutil
from dateutil.parser import parse
import urllib
#from google.appengine.api.datastore_errors import Timeout
from google.appengine.api import taskqueue

import re

#try:
#  pass
#except Timeout:
#  pass
#import sys
#sys.setdefaultencoding('utf-8')


class Feed():
	title = ""
	uri = ""
	error  = ""
	content = ""
	date = None

	@staticmethod
	def get_by_key_name(uri):
		data = memcache.get("feed:"+uri)
		if data:
			feed = Feed()
			feed.title = data.title
			feed.uri = data.uri
			feed.error = data.error
			feed.content = data.content
			return feed
		else:
			return None
		
	def put(self):
		self.date = datetime.datetime.now()
		memcache.set("feed:"+self.uri,self,60*60*24*3)
		
		#直近30にいれる
		list = memcache.get("list")
		if not list:
			list = []
		if not self in list:
			list.insert(0,self)
			memcache.set("list",list[0:30],60*60*24)

	@staticmethod
	def get_list():
		return memcache.get("list")
		

	def cache_expired(self):
		data = memcache.get("cached:" + self.uri)
		if not data:
			memcache.add("cached:" + self.uri, "OK", 60*20)
			return True
		else:
			return False
		#get from cache or not?
		#difftime = datetime.datetime.now() - self.date
		#if difftime.seconds > 20*60 and self.content:
		#	return True
		#else:
		#	return False
			
	def parse(self):
		
		try:
			return pickle.loads(str(self.content))
		except:
			return None
		
	def fetch(self):
		try:
			result = urlfetch.fetch(self.uri.encode("utf-8"))
		except:
			self.error = "Can't Fetch"
			return None
		if result.status_code != 200:
			self.error = "Can't Fetch (%d)" % result.status_code
			return None
			
		try:
			rss = feedparser.parse(result.content)
		except:
			self.error = "Wrong RSS Format"
			return None
			
		if not rss or rss.bozo == 1:
			self.error = "Wrong RSS Format"
			return rss
		self.error = ""
		self.title = rss.channel.title
		self.content = pickle.dumps(rss).decode("utf-8","ignore") #result.content.decode("utf-8", "ignore")
		return rss

			
class Option(object):
	cs = "def"
	mc = "5"
	st = "d"
	tm = "s"
	
	def __init__(self, request):
		self.cs = request.get('cs',self.cs)
		self.mc = request.get('mc',self.mc)
		self.st = request.get('st',self.st)
		self.tm = request.get('tm',self.tm)	
		if not self.mc.isdigit():
			self.mc = "5"
	
def parse_feed(feed_url):
	#Responseオブジェクトを取得
	result = urlfetch.fetch(feed_url)
	if result.status_code == 200:
		d = feedparser.parse(result.content)
	else:
		raise Exception("Can not retrieve given URL.")
	#RSSの形式が規格外の場合(bozo=まぬけ)
	if d.bozo == 1:
		raise Exception("Can not parse given URL.")
	return d	


class MainPage(webapp.RequestHandler):

    def get(self):
		feeds = Feed.get_list()
		
		for feed in feeds:
			if feed.date:
				feed.diffmin =  datetime.datetime.now() - feed.date
				feed.diffmin =  int(feed.diffmin.seconds / 60)
			feed.escaped_uri = urllib.quote(feed.uri.encode("utf-8"))	
			
		template_values = {
			"SITE_NAME":"Tomato Feed",
			"SITE_SUBTITLE":"ホームページにブログ記事の新着を表示",
			'feeds': feeds,
			'feeds_count': len(feeds),
		}
	
		path = os.path.join(os.path.dirname(__file__), 'views/home.html')
		self.response.out.write(template.render(path, template_values))
	
class FeedPage(webapp.RequestHandler):
	def get(self):
		feeduri = self.request.get('uri')

		option = Option(self.request)

		template_values = {
			"SITE_NAME":"Tomato Feed",
			"rss_uri" : feeduri,
			"option" : option,
			"local_js_uri" : "/jsout.php?"+os.environ['QUERY_STRING'],
			"js_uri" : "http://"+os.environ['SERVER_NAME'] + "/jsout.php?"+os.environ['QUERY_STRING'],
		}
		path = os.path.join(os.path.dirname(__file__), 'views/detail.html')
		self.response.out.write(template.render(path, template_values))
		
def sorter(a, b):
	return cmp(a.updated_time, b.updated_time)

class Jsout(webapp.RequestHandler):

	def get(self):
		#Find existing feed
		uri = self.request.get('uri')
		format = self.request.get('format')

		feed = Feed.get_by_key_name(uri)
		if feed is None:
			#new feed
			feed = Feed()
			feed.uri = uri
			rss = feed.fetch()
			if not feed.error:
				feed.put()
		else:
			#existing feed
			rss = feed.parse()
			if feed.cache_expired():
				taskqueue.add(url='/fetch', params={'uri': uri}, method = 'GET')
		
		if not rss:
			self.response.out.write('document.write("<ul><li>Error: '+feed.error+'</li></ul>")')
			return
		
		option = Option(self.request)
		for entry in rss.entries:
			try:
				test = parse(entry.updated)
			except:
				test = datetime.datetime.now()
			entry.updated_time = test.strftime('%Y/%m/%d %H:%M:%s')
			timef = ""
			if option.tm == "s":
				timef = '%m/%d'
			elif option.tm == "m":
				timef = '%Y/%m/%d'
			elif option.tm == "l":
				timef = '%Y/%m/%d %H:%M'
			
			if option.tm != "n":
				entry.updated_format = test.strftime(timef)	
			entry.title = re.sub("[\r\n]"," ",entry.title)

		if option.st == "s":
			rss.entries.sort(sorter) 
			
		if option.mc > 0:
			rss.entries = rss.entries[0:int(option.mc)]

		
		
		template_values = {
			"SITE_NAME":"Tomato Feed",
			"APP_URI":"http://"+os.environ['SERVER_NAME'],
			"rss_uri" : uri,
			"option" : option,
			"entries" : rss.entries,
			'entries_count': len(rss.entries),
		}

		if format == 'html':
			path = os.path.join(os.path.dirname(__file__), 'views/list.html')
		else:
			self.response.headers["Content-Type"] = "application/x-javascript;charset=utf-8;"
			path = os.path.join(os.path.dirname(__file__), 'views/list.js')
		self.response.out.write(template.render(path, template_values))

class FetchFeed(webapp.RequestHandler):

	def get(self):
		#Find existing feed
		uri = self.request.get('uri')
		self.response.headers["Content-Type"] = "text/plain;charset=utf-8;"

		feed = Feed.get_by_key_name(uri)
		if feed:
			feed.fetch()
			feed.put()
			self.response.out.write(u"Fetched:%s\n" % uri)
		else:
			self.response.out.write('NG\n')
			
		
class Custom(webapp.RequestHandler):
	def get(self):
		template_values = {
		"SITE_NAME":"Tomato Feed",
		}
		path = os.path.join(os.path.dirname(__file__), 'views/custom.html')
		self.response.out.write(template.render(path, template_values))

application = webapp.WSGIApplication(
                                     [('/', MainPage),
                                     ('/feed', FeedPage),
                                     ('/jsout.php', Jsout),
                                     ('/fetch', FetchFeed),
                                     ('/custom', Custom)],
                                     debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()