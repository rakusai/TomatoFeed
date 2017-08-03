# -*- coding: utf-8 -*-

import webapp2

import sys
import os
import cgi
import re
import datetime
import urllib

from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from lib import dateutil
from lib.dateutil.parser import parse
from lib import feedparser

class Entry():
  updated = None
  title = ''
  link = ''

class Feed():
  title = ''
  uri = ''
  error  = ''
  entries = []
  date = None

  @staticmethod
  def get_by_key_name(uri):
    data = memcache.get('log:' + uri)
    if data:
      feed = Feed()
      feed.title = data.title
      feed.uri = data.uri
      feed.error = data.error
      feed.entries = data.entries
      return feed
    else:
      return None

  def put(self):
    self.date = datetime.datetime.now()
    memcache.set('log:' + self.uri, self, 60*60*24*3)

    #直近30にいれる
    list = memcache.get('rlist')
    if not list:
      list = []
    if not self in list:
      list.insert(0, self)
      memcache.set('rlist', list[0:30], 60*60*24)

  @staticmethod
  def get_list():
    list =  memcache.get('rlist')
    return list or []

  def cache_expired(self):
    data = memcache.get('cached:' + self.uri)
    if not data:
      memcache.add('cached:' + self.uri, 'OK', 60*20)
      return True
    else:
      return False
    #get from cache or not?
    #difftime = datetime.datetime.now() - self.date
    #if difftime.seconds > 20*60 and self.content:
    #  return True
    #else:
    #  return False

  def fetch(self):
    try:
      result = urlfetch.fetch(self.uri.encode('utf-8'))
    except:
      self.error = 'Can’t Fetch'
      return None
    if result.status_code != 200:
      self.error = 'Can’t Fetch (%d)' % result.status_code
      return None

    try:
      rss = feedparser.parse(result.content)
    except:
      self.error = 'Wrong RSS Format'
      return None

    if not rss or rss.bozo == 1:
      self.error = 'Wrong RSS Format'
      return None

    #URL, タイトル、日付だけ取り出す
    self.error = ''
    self.title = rss.channel.title
    self.entries = []
    for entry in rss.entries:
      e = Entry()
      e.title = entry.title
      e.link = entry.link
      e.updated = entry.updated
      self.entries.append(e)

    return self


class Option(object):
  cs = 'def'
  mc = '5'
  st = 'd'
  tm = 's'

  def __init__(self, request):
    self.cs = request.get('cs', self.cs)
    self.mc = request.get('mc', self.mc)
    self.st = request.get('st', self.st)
    self.tm = request.get('tm', self.tm)
    if not self.mc.isdigit():
      self.mc = '5'

class MainPage(webapp.RequestHandler):
  def get(self):
    feeds = Feed.get_list()

    for feed in feeds:
      if feed.date:
        feed.diffmin =  datetime.datetime.now() - feed.date
        feed.diffmin =  int(feed.diffmin.seconds / 60)
      feed.escaped_uri = urllib.quote(feed.uri.encode('utf-8'))

    template_values = {
      'SITE_NAME': 'Tomato Feed',
      'SITE_SUBTITLE': 'ホームページにブログ記事の新着を表示',
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
      'SITE_NAME': 'Tomato Feed',
      'rss_uri': feeduri,
      'option': option,
      'local_js_uri': '/jsout.php?' + os.environ['QUERY_STRING'],
      'js_uri': 'http://' + os.environ['SERVER_NAME'] + '/jsout.php?' + os.environ['QUERY_STRING'],
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
    if not feed:
      #new feed
      feed = Feed()
      feed.uri = uri
      feed.fetch()
      if not feed.error:
        feed.put()
    else:
      #existing feed
      if feed.cache_expired():
        taskqueue.add(url = '/fetch', params = {'uri': uri}, method = 'GET')

    if not feed or feed.error:
      self.response.out.write("document.write('<ul><li>Error: " + feed.error + "</li></ul>')")
      return

    option = Option(self.request)

    def get_updated_format(parsed_time):
      if option.tm == 'n':
        return ''

      timef = ''
      if option.tm == 's':
        timef = '(%m/%d)'
      elif option.tm == 'm':
        timef = '(%Y/%m/%d)'
      elif option.tm == 'l':
        timef = '(%Y/%m/%d %H:%M)'
      else:
        timef = option.tm

      return parsed_time.strftime(timef)

    for entry in feed.entries:
      try:
        parsed_time = parse(entry.updated)
      except:
        parsed_time = datetime.datetime.now()
      entry.updated_time = parsed_time.strftime('%Y/%m/%d %H:%M:%s')
      entry.updated_format = get_updated_format(parsed_time)
      entry.title = re.sub('[\r\n]', ' ', entry.title)

    if option.st == 's':
      feed.entries.sort(sorter)

    if option.mc > 0:
      feed.entries = feed.entries[0:int(option.mc)]

    template_values = {
      'SITE_NAME': 'Tomato Feed',
      'APP_URI': 'http://' + os.environ['HTTP_HOST'],
      'rss_uri': uri,
      'option': option,
      'entries': feed.entries,
      'entries_count': len(feed.entries),
    }

    if format == 'html':
      path = os.path.join(os.path.dirname(__file__), 'views/list.html')
    else:
      self.response.headers['Content-Type'] = 'application/x-javascript;charset=utf-8;'
      path = os.path.join(os.path.dirname(__file__), 'views/list.js')
    self.response.out.write(template.render(path, template_values))

class FetchFeed(webapp.RequestHandler):

  def get(self):
    #Find existing feed
    uri = self.request.get('uri')
    self.response.headers['Content-Type'] = 'text/plain;charset=utf-8;'

    feed = Feed.get_by_key_name(uri)
    if feed:
      feed.fetch()
      feed.put()
      self.response.out.write(u'Fetched:%s\n' % uri)
    else:
      self.response.out.write('NG\n')

class Custom(webapp.RequestHandler):
  def get(self):
    template_values = {
      'SITE_NAME': 'Tomato Feed',
    }
    path = os.path.join(os.path.dirname(__file__), 'views/custom.html')
    self.response.out.write(template.render(path, template_values))

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/feed', FeedPage),
                               ('/jsout.php', Jsout),
                               ('/fetch', FetchFeed),
                               ('/custom', Custom)],
                               debug=True)
'''
def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
'''
