# Memojo Reddit reader

A read-only script that lists the newest posts of a few photo-related subreddits so that the founder of Memojo (a photo app that keeps everything on the phone) can notice people asking about photo problems and answer them himself, from his own account, with his affiliation stated.

What it does on Reddit: once a day, it reads the new-posts listing and the rules of a small set of subreddits through the official Data API (app-only token, type "script"), matches posts against a short phrase list ("can't find a photo", "too many photos", "alternative to Google Photos") and writes the matches to a JSON file. Without API credentials it reads the public Atom feeds Reddit publishes for feed readers instead.

What it never does: post, comment, vote, message, follow, edit, or hold anyone's credentials but the author's own. About 100 requests a day, one request per second at most. Stored data is the post link, date, public username and an excerpt of at most 200 characters, deleted after 30 days. Nothing is resold, shared or used for training.

Run: `python3 reddit_fetch.py --client-id ID --secret SECRET --user USERNAME --out leads.json`
