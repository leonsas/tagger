"""Top level module for your Flask application."""
import json, time
import datetime as dt
import logging
from requests import ConnectionError
# Import the Flask Framework
from flask import Flask
from flask import redirect, request

from google.appengine.ext import ndb

import pocket
from pocket import Pocket

from conf import POCKET_CONSUMER_KEY as POCKET_KEY
app = Flask(__name__)
# Note: We don't need to call run() since our application is embedded within
# the App Engine WSGI application server.
@app.route('/')
def hello():
    """Return a friendly HTTP greeting."""
    return 'Pocket article tagger. /auth_pocket to signup.'

@app.route('/auth_pocket')
def auth_pocket():
    """Redirect user to Pocket's auth website"""

    request_token = Pocket.get_request_token(consumer_key=POCKET_KEY)
    redirect_uri = "http://pocket-tagger.appspot.com/get_credentials?code=" + request_token
    print request_token, redirect_uri
    auth_url = Pocket.get_auth_url(code=request_token, redirect_uri=redirect_uri)
    return redirect(auth_url, code=302)

@app.route('/get_credentials')
def get_credentials():
    user_request_token = request.args.get('code','')
    user_credentials = Pocket.get_credentials(consumer_key=POCKET_KEY, code=user_request_token)
    access_token = user_credentials['access_token']
    pocketier = Pocketier()
    pocketier.token = access_token
    pocketier.put()
    return "Great, your articles will be tagged every 30min or so."


@app.route('/tag_now')
def tag_now():
    pocketiers = Pocketier.query()
    for pocketier in pocketiers:
        articles = get_all_articles(pocketier)
        if articles == None:
            continue
        pocket_instance = Pocket(POCKET_KEY, pocketier.token)
        tag_articles(articles, pocket_instance)
        pocketier.last_tagged = dt.datetime.utcnow()
        pocketier.put()
    return "Tagged"

def get_all_articles(pocketier):
    pocket_instance = Pocket(POCKET_KEY, pocketier.token)
    if pocketier.last_tagged is None:
        since = None
    else:
        since = int(time.mktime(pocketier.last_tagged.timetuple()))
    logging.info("last_tagged: %s" % pocketier.last_tagged)
    data, headers = pocket_instance.get(since=since)
    #'list' is actually a dict, unless its empty, in which case it's a dict
    if hasattr(data['list'], 'values'):
        articles = data['list'].values()
        logging.info("Number of articles = %s" % len(articles))
        return articles
    else:
        return None

def tag_articles(articles, pocket_instance):
    chunk_size = 35
    chunks = zip(*[iter(articles)]*chunk_size) #chunk article list
    for i, chunk in enumerate(chunks):
        for art in chunk:
            if 'word_count' not in art.keys():
                continue
            w = int(art['word_count'])
            if w < 500: tag = "quick"
            elif w < 1000: tag = "short"
            elif w < 2000: tag = "mid"
            else: tag = "long"
            pocket_instance = pocket_instance.tags_add(int(art['item_id']), tag)
        _commit_pocket(pocket_instance)

def _commit_pocket(pocket_instance):
    try:
        logging.info("Commiting chunk")
        pocket_instance.commit()
    except ConnectionError:
        #Usually happens with a timeout, so retry
        logging.info("Fail to commit chunk, retrying")
        _commit_pocket(pocket_instance)

@app.errorhandler(404)
def page_not_found(e):
    """Return a custom 404 error."""
    return 'Sorry, Nothing at this URL.', 404


@app.errorhandler(500)
def page_not_found(e):
    """Return a custom 500 error."""
    return 'Sorry, unexpected error: {}'.format(e), 500

class Pocketier(ndb.Model):
    token = ndb.StringProperty(indexed=False)
    last_tagged = ndb.DateTimeProperty(auto_now_add=False)