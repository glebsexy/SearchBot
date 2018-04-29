""" VK Search Bot

This bot searches for new posts on specified queries. Each user could have their own list of searches. Users could add and remove queries by talking to the bot.

TODO:
	* Add more inteligence with Regex or Wit.ai
	* Russian and English translation
	* Make the bot remember the context
	
"""
import time
from lxml import html
import requests
import json
import logging
import logging.handlers

from vk_info import token, version, service_token

LOG_FILE = 'bot.log'
LM_FILE, DB_FILE = "lm.json", "db.json"

# Set up a specific logger with our desired output level
blogger = logging.getLogger('BotLogger')
blogger.setLevel(logging.DEBUG)

# Add the log message handler to the logger
handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes = 10 * 1024 * 1024, backupCount = 3)
bf = logging.Formatter(fmt = '%(asctime)s %(levelname)s: %(message)s', datefmt='%Y.%m.%d %H:%M:%S', style='%')
handler.setFormatter(bf)
blogger.addHandler(handler)

"""
Texts used to talk to the user

Args:
	q: query
	g: group
"""
text_hello = "Привет!"
text_unclear = "Я не понимаю тебя. :c"
text_help = "Доступные команды:\n- Добавь <поисковый запрос> [в группе <URL группы>]\n- Удали <поискавый запрос> [для группы <URL группы>]\n- Удали <URL группы> (перестать искать все запросы в этой группе)"
text_super = "Супер!"
text_okay = "Окей!"
text_added = "Буду оповещать, если новые результаты по запросу \"{q}\" будут появляться в сообществе \"{g}\"."
text_wrong_data = "Что-то это не то."
text_ask_group = "В какой группе искать? Скинь ссылку, пожалуйста."
text_removed = "Больше не буду оповещать о новых записях с \"{q}\" в сообществе \"{g}\"."
text_removed_query = "Больше не буду оповещать о новых записях по запросу \"{q}\"."
text_removed_group = "Больше не буду оповещать о новых записях в сообществе \"{g}\"."
text_cant_find_group = "Не могу найти группу с таким адресом. о_О"
text_you_are_welcome = "Пожалуйста!"

"""  
Data structure:

{ 
	user : { 
		query : [
			{ owner_id : last_post },
			{ owner_id : last_post }
			]
	} 
}

"""

def main():
	counter = 0
	while(True):
		counter += 1

		# Check messages and reply
		all_messages = get_messages()
		messages = filter_new_messages(all_messages)
		if not messages:
			blogger.debug("No new messages.")
		else:
			# They need to be reversed in order to be answered sequentially
			for message in reversed(messages):
				blogger.debug("New messages found!")
				reply_success = reply_to_message(message['user_id'], message['body'])
				if not reply_success:
					# TODO: save intent and wait for response
					blogger.debug("Reply was successful: {}".format(reply_success))
				pass
			set_file_data(LM_FILE, get_last_message(messages))
		
		blogger.debug("Checked messages {} times.".format(counter))
		if counter % 50 != 0:
			time.sleep(3)
			continue

		# Search
		search_all()	
		time.sleep(3)


def get_messages():
	""" Gets messages after the last one """
	last_message = get_file_data(LM_FILE)
	if not last_message:
		values = {'access_token': token, 'v': version, 'out': 0, 'count': 100, 'time_offset': 0}
	else:	
		values = {'access_token': token, 'v': version, 'out': 0, 'count': 200, 'last_message_id': last_message['id'], 'time_offset': 0}
	try:
		r = requests.get('https://api.vk.com/method/messages.get', params = values)
		q = r.json()
		messages = q['response']['items']
		return messages
	except KeyError as e:
		blogger.error("KeyError: {}".format(e))
		blogger.error("Received data: {}".format(q))
		return []
	except requests.exceptions.RequestException as e:
		blogger.error("Get messages request error: {}".format(e))
		return []

def filter_new_messages(messages):
	""" Filter only new messages out """
	last_message = get_file_data(LM_FILE)
	if not last_message:
		return messages
	new_messages = []
	for message in messages:
		if message['date'] > last_message['date']:
			new_messages.append(message)
	return new_messages


def reply_to_message(user, message):
	""" Given a message, find the best answer to it and act upon it

	Returns:
		True if the reply was enough, False if it's necessary to wait for a user to reply. 
	"""
	user = str(user)
	new_user = add_user(user)
	owner_id = None
	query, screen_name = extract_query(message)
	if screen_name is not None:
		group = get_group_info(screen_name)
		if group:
			owner_id = -group['id']
			group_name = group['name']
		else:
			send_message(user, text_cant_find_group)
			return True
	
	while "Удали" in message or "удали" in message:
		if "обавь" in message:
			break
		remove_query(user, query, owner_id)
		if owner_id is not None and query is not None:
			send_message(user, text_removed.format(q = query, g = group_name))
			return True
		elif owner_id is not None and query is None:
			send_message(user, text_removed_group.format(g = group_name))
			return True
		elif owner_id is None and query is not None: 
			send_message(user, text_removed_query.format(q = query))
			return True
		else:
			send_message(user, text_unclear)
			return True
		break

	if owner_id is not None and query is not None:
		add_query(user, query, owner_id)
		send_message(user, text_added.format(q = query, g = group_name))
		return True

	if "ривет" in message or "Хай" in message or "хай" in message or "ку" in message or "Ку" in message or "дравствуй" in message:
		send_message(user, text_hello)
		if new_user:
			send_message(user, text_help)
		return True
	if "омощь" in message or "оманды" in message:
		send_message(user, text_help)
		return True
	if "асибо" in message or "лагодар" in message:
		send_message(user, text_you_are_welcome)

	# None of the filters matched
	send_message(user, text_unclear)
	return True

def send_message(user, text):
	""" Sends the text message to the user """
	values = {'access_token': token, 'v': version, 'peer_id': user, 'message': text}
	try:
		requests.get('https://api.vk.com/method/messages.send', params = values)
	except requests.exception.RequestException as e:
		blogger.error("Send message request exception: {}".format(e))
		return

def send_post(user, post):
	""" Sends a VK wall post to the user """
	attachment = "{}{}_{}".format("wall", post['owner_id'], post['id'])
	values = {'access_token': token, 'v': version, 'peer_id': user, 'attachment': attachment}
	try:
		requests.get('https://api.vk.com/method/messages.send', params = values)
	except requests.exception.RequestException as e:
		blogger.error("Send post request exception: {}".format(e))
		return
	

def extract_query(m):
	""" Tries to understand a query and/or owner_id from the user's message """
	q, g = None, None
	try:
		words = m.split(" ")
		if "vk.com/" in m:
			g = m.split("vk.com/", 1)[1].split(" ")[0]
		if g is None and " в группе " in m:
			g = m.split(" в группе ", 1)[1].split(" ")[0]
		elif g is None and " в " in m:
			g = m.split(" в ", 1)[1].split(" ")[0]
		if "\"" in m:
			q = m.split("\"", 2)[1]
			return q, g
		if "обавь" in words[0] or "дали" in words[0]:
			if "vk.com/" not in words[1]:
				q = words[1]
	except Exception as e:
		blogger.warning("Query extraction failed: {}".format(e))
		pass
	return q, g

def add_user(u):
	""" Adds a user to the database
	
	Returns:
		If the user is new — True. False if they already were in the DB.
	"""
	db = get_file_data(DB_FILE)
	# User ID is a number — convert it to string
	u = str(u)
	if u not in db:
		blogger.debug("Welcome new user! Adding...")
		db[u] = {}
		set_file_data(DB_FILE, db)
		return True
	return False

def add_query(u, q = None, g = None):
	""" Adds a query and a owner_id to the query of a specified user """
	blogger.debug("Adding a query...")
	db = get_file_data(DB_FILE)

	if u not in db:
		blogger.debug("Adding a user to DB.")
		add_user(u)
		db = get_file_data(DB_FILE)
	if q is not None and q not in db[u]:
		blogger.debug("Adding a query to DB.")
		db[u][q] = {}

	if g is not None and g not in db[u][q]:
		blogger.debug("Adding an owner ID to the query.")
	
		all_posts = search_posts(g, q)
		posts, replies = separate_posts_and_replies(all_posts)

		if posts:
			db[u][q][g] = posts[0]['id']
		else:
			db[u][q][g] = ""

	set_file_data(DB_FILE, db)

def remove_query(u, q = None, g = None):
	""" Removes query and owner_id from the list of the specified user """
	blogger.debug("Removing user {} query {} on {}".format(u, q, g))
	db = get_file_data(DB_FILE)
	if u not in db:
		blogger.debug("User not in DB tried to remove something.")
		return

	# If only query is present then remove it
	if q is not None and g is None:
		popped = db[u].pop(q, None)
		blogger.debug("Popped query: {}".format(popped))

	# If both query and owner ID are present, remove owner ID in query
	elif q is not None and g is not None:
		g = str(g)
		if q in db[u]:
			popped = db[u][q].pop(g, None)
			blogger.debug("Popped group {} from query: {}".format(g, popped))
		
	# Remove all appearences of a owner_id in all queries
	elif g is not None:
		g = str(g)
		blogger.debug("No query to remove (q = {}), trying to remove owner IDs (id = {}).".format(q, g))
		for query in db[u]:
			popped = db[u][query].pop(g, None)
			blogger.debug("Popped group {} from query {}.".format(popped, query))

	set_file_data(DB_FILE, db)

def get_last_message(messages):
	""" Get last message from the array of messages """
	lm = messages[0]
	for message in messages:
		if message['date'] > lm['date']:
			lm = message
	return lm
	
def get_file_data(file_address):
	""" Read JSON data from file
	Args:
		file_address: address of a file in the file system

	Returns:
		Object that was read from the file (dict or list)
	"""
	with open(file_address, 'r', encoding='utf-8') as f:
		return json.load(f)

def set_file_data(file_address, data):
	""" Write JSON data to file

	Args:
		file_address: address of a file in the file system
		data: object (dict or list) to be written to the file
	"""
	with open(file_address, 'w', encoding='utf-8') as f:
		f.seek(0)
		json.dump(data, f, indent = 4, ensure_ascii = False)
		f.truncate()

def search_all():
	""" Search for all queries of all users """
	db = get_file_data(DB_FILE)
	blogger.debug("Searching:")
	for user in db:
		for query in db[user]:
			for owner_id in db[user][query]:
				blogger.debug("User: {}, query: {}, owner_id: {}".format(user, query, owner_id))
				all_posts = search_posts(owner_id, query)
				posts, replies = separate_posts_and_replies(all_posts)
				new_posts = filter_new_posts(user, query, owner_id, posts)
				blogger.debug("Found {} new posts.".format(len(new_posts)))
				if new_posts:
					for post in new_posts:
						send_post(user, post)
			

def search_posts(owner_id, query):
	""" Search the page for posts matching the query """
	values = {'access_token': service_token, 'v': version, 'owner_only': 0, 'count': 10, 'owner_id': owner_id, 'query': query}
	try:
		r = requests.get('https://api.vk.com/method/wall.search', params = values)
		q = r.json()
		posts = q['response']['items']
		return posts
	except KeyError as e:
		blogger.error("KeyError: {}".format(e))
		blogger.error("Received data: {}".format(q))
		return []
	except requests.exceptions.RequestException as e:
		blogger.error("Search posts request error: {}".format(e))
		return []

def separate_posts_and_replies(items):
	""" Search includes both comments and posts, this function separates them into two lists. """
	posts, replies = [], []
	for item in items:
		if item['post_type'] == 'reply':
			replies.append(item)
		else:
			posts.append(item)
	return posts, replies

def filter_new_posts(user, query, owner_id, posts):
	""" Filter only posts which were not yet sent to the user. """
	# Return empty if came empty
	if not posts:
		return []
	# Get the post which is the last currently
	db = get_file_data(DB_FILE)
	last_post = db[user][query][owner_id]
	
	# Last post is currently the latest, no new posts
	if last_post == posts[0]['id']:
		return []

	# The first post will always be the last one
	update_last_post(user, query, owner_id, posts[0]['id'])

	# If a post wasn't listed, add it and return all posts as they are new
	if last_post == "":
		blogger.debug("--- Last post wasn't present, adding.")
		update_last_post(user, query, owner_id, posts[0]['id'])
		return posts

	# Find the current last post in the list
	last_found = -1
	for i in range(len(posts)):
		if posts[i]['id'] == last_post:
			last_found = i
	# If not found — all posts are new and the current last one is below
	if last_found < 0:
		return posts
	# Return posts preceding the current last one
	return posts[:last_found]

def update_last_post(user, query, owner_id, post_id):
	""" If new posts are found, the previous last post needs to be updated. """
	db = get_file_data(DB_FILE)
	db[user][query][owner_id] = post_id
	set_file_data(DB_FILE, db)

def get_group_info(screen_name):
	""" Get name and ID of a group. """
	values = {'access_token': token, 'v': version, 'group_ids': screen_name}
	try:
		r = requests.get('https://api.vk.com/method/groups.getById', params = values)
		q = r.json()
		group = q['response'][0]
		return group
	except KeyError as e:
		blogger.error("KeyError: {}".format(e))
		blogger.error("Received data: {}".format(q))
		return []
	except requests.exceptions.RequestException as e:
		blogger.error("Get group by ID request error: {}".format(e))
		return []

def search(page, query):
	""" Search the page for posts matching the query """
	page = requests.get("https://m.vk.com/{}?q={}".format(page, query))
	tree = html.fromstring(page.content)

	posts_raw = tree.xpath('//div[contains(@class, "pi_text")]')
	posts_str = []
	for post in posts_raw:
		posts_str.append("".join(post.xpath('descendant-or-self::text()')))
	
	blogger.debug(posts_str)
	return page_name, posts_id, posts_str

def get_page_name(page):
	""" Get the title of the page """
	page = requests.get("https://m.vk.com/{}".format(page))
	tree = html.fromstring(page.content)
	page_name = tree.xpath('//h2[contains(@class, "basisGroup__groupTitle op_header")]/text()')
	return page_name


if __name__ == "__main__":
	main()






