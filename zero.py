""" VK Search Bot

This bot searches for new posts on specified queries. Each user could have their own list of searches. Users could add and remove queries by talking to the bot.

TODO:
	* Russian and English translation
	* Make the bot remember the context
	
"""
import time
import vk
from lxml import html
import requests
import json

from vk_info import token, version

lm_file, db_file = "lm.json", "db.json"

"""
Texts used to talk to the user

Args:
	q: query
	g: group
"""
text_hello = "Привет!"
text_unclear = "Я не понимаю тебя. :c"
text_help = "Доступные команды:\n- Добавь <поисковый запрос> [в группе <URL группы>]\n- Удали <поискавый запрос> [для группы <URL группы>]\n- Отписаться (от всех поисков; можно заново \"подписаться\")"
text_super = "Супер!"
text_okay = "Окей!"
text_added = "Буду оповещать, если новые результаты по запросу \"{q}\" будут появляться в сообществе \"{g}\"."
text_wrong_data = "Что-то это не то."
text_ask_group = "В какой группе искать? Скинь ссылку, пожалуйста."
text_removed = "Больше не буду оповещать о новых записях с \"{q}\" в сообществе \"{g}\"."

"""  
Data structure:

{ 
	user : { 
		query : [
			{ group : last_post },
			{ group : last_post }
			]
	} 
}

"""

def main():
	while(True):
		all_messages = get_messages()
		messages = filter_new_messages(all_messages)
		if not messages:
			print("No new messages!")
			time.sleep(3)
			continue
		# They need to be reversed in order to be answered sequentially
		for message in reversed(messages):
			print("New messages found!")
			print(messages)
			reply_success = reply_to_message(message['user_id'], message['body'])
			if not reply_success:
				# TODO: save intent and wait for response
				print("Reply was successful: ", reply_success)
				pass
		set_file_data(lm_file, get_last_message(messages))
		time.sleep(3)


def get_messages():
""" Gets messages after the last one """
	last_message = get_file_data(lm_file)
	if not last_message:
		values = {'access_token': token, 'v': version, 'out': 0, 'count': 100, 'time_offset': 0}
		print("Getting messages, last message is None.")
	else:	
		values = {'access_token': token, 'v': version, 'out': 0, 'count': 200, 'last_message_id': last_message['id'], 'time_offset': 0}
		print("Getting messages, last messages is ", last_message['id'])
	try:
		r = requests.get('https://api.vk.com/method/messages.get', params = values)
		q = r.json()
		messages = q['response']['items']
		return messages
	except KeyError as e:
		print("KeyError: ", e)
		print("Received data: ", q)
		return []
	except requests.exceptions.RequestException as e:
		print("Get messages request error: ", e)
		return []

def filter_new_messages(messages):
""" Filter only new messages out """
	last_message = get_file_data(lm_file)
	if not last_message:
		print("Filtering, last message is None.")
		return messages
	new_messages = []
	for message in messages:
		if message['date'] > last_message['date']:
			print("Filtering: ", message['date'], " is larger than ", last_message['date'])
			new_messages.append(message)
	return new_messages


def reply_to_message(user, message):
""" Given a message, find the best answer to it and act upon it

Returns:
	True if the reply was enough, False if it's necessary to wait for a user to reply. 
"""
	user = str(user)
	add_user(user)
	print("Choosing the reply...")
	query, group = extract_query(message)
	if "Удали" in message or "удали" in message:
		remove_query(user, query, group)
		if group is not None and query is not None:
			send_message(user, text_removed.format(q = query, g = group))
			return True
		elif group is not None and query is None:
			send_message(user, text_removed_group)
			return True
		elif group is None and query is not None: 
			send_message(user, text_removed_query)
			return True
		elif "обавь" in message:
			pass
		else:
			send_message(user, text_unclear)
			return True

	if group is not None and query is not None:
		add_query(user, query, group)
		send_message(user, text_added.format(q = query, g = group))
		return True
	elif group is not None and query is None:
		send_message(user, text_ask_query)
		return False
	elif group is None and query is not None: 
		send_message(user, text_ask_group)
		return False

	if "ривет" in message:
		send_message(user, text_hello)
		return True
	if "омощь" in message or "оманды" in message:
		send_message(user, text_help)
		return True
	if "тписаться" in message:
		send_message(user, text_unsubscribed)
		return True
	if "одписаться" in message:
		send_message(user, text_subscribed)
		return True
	# None of the filters matched
	send_message(user, text_unclear)
	return True

def send_message(user, text):
""" Sends the text message to the user """
	values = {'access_token': token, 'v': version, 'peer_id': user, 'message': text}
	try:
		requests.get('https://api.vk.com/method/messages.send', params = values)
	except requests.exception.RequestException as e:
		print("Send message request exception: ", e)
		return

def send_post(user, post):
""" Sends a VK wall post to the user TODO """
	values = {'access_token': token, 'v': version, 'peer_id': user, 'message': text}
	try:
		requests.get('https://api.vk.com/method/messages.send', params = values)
	except requests.exception.RequestException as e:
		print("Send post request exception: ", e)
		return
	

def extract_query(m):
""" Tries to understand a query and/or group from the user's message """
	q, g = None, None
	try:
		words = m.split(" ")
		if "vk.com/" in m:
			g = m.split("vk.com/", 1)[1].split(" ")[0]
		if "\"" in m:
			q = m.split("\"", 2)[1]
			return q, g
		if "обавь" in words[0] or "дали" in words[0]:
			q = words[1]
	except Exception as e:
		print("Query extraction failed: ", e)
		pass
	return q, g

def add_user(u):
""" Adds a user to the database """
	db = get_file_data(db_file)
	# User ID is a number — convert it to string
	u = str(u)
	if u not in db:
		print("Adding a user...")
		db[u] = {}
		set_file_data(db_file, db)

def add_query(u, q = None, g = None):
""" Adds a query and a group to the query of a specified user """
	print("Adding a query...")
	db = get_file_data(db_file)

	if u not in db:
		print("User is not in the db")
		add_user(u)
		
	if q is not None and q not in db[u]:
		print("q is not None and q not in db[u]")
		db[u][q] = {}

	if g is not None and g not in db[u][q]:
		print("g is not None and g not in db[u][q]")
		db[u][q][g] = ""

	set_file_data(db_file, db)

def remove_query(u, q = None, g = None):
""" Removes query and group from the list of the specified user """
	try:
		db = get_file_data(db_file)
		if u not in db:
			print("User not in DB tried to remove sth.")
			return
		if q is None or q not in db[u]:
			print("No query to remove.")
			# Remove all appearences of a group in all queries
			if g is not None:
				for query in db[u].keys():
					if g in db[u][query]:
						db[u][query].pop(g)
		else:
			db[u].pop(q, None)

		set_file_data(db_file, db)

	except Exception as e:
		print("Removing a query failed: ", e)
		pass

def get_last_message(messages):
""" Get last message from the array of messages """
	lm = messages[0]
	for message in messages:
		if message['date'] > lm['date']:
			print(message['date'], " is larger than ", lm['date'])
			lm = message
	return lm
	
def get_file_data(file_address):
""" Get JSON data from file """
	with open(file_address, 'r', encoding='utf-8') as f:
		return json.load(f)

def set_file_data(file_address, data):
""" Set file to JSON data """
	with open(file_address, 'w', encoding='utf-8') as f:
		f.seek(0)
		json.dump(data, f, indent = 4, ensure_ascii = False)
		f.truncate()

def search(page, query):
""" Search the page for posts matching the query """
	page = requests.get("https://m.vk.com/{}?q={}".format(page, query))
	tree = html.fromstring(page.content)
	
	posts_raw = tree.xpath('//div[contains(@class, "pi_text")]')
	posts_str = []
	for post in posts_raw:
		posts_str.append("".join(post.xpath('descendant-or-self::text()')))
	
	print(posts_str)


if __name__ == "__main__":
	main()






