# SearchBot
A bot that should notify you about new posts in the groups you want.

## Flow
1. Human asks a bot to add "query in group" to the search list.
2. Bot periodically searches that group for the query.
3. Bot messages the human if it finds a new post for that query.
4. At any time the human can remove the query.

## Flaws
- Bot can't search too often as VK stops sending new results for a certain period of time.
