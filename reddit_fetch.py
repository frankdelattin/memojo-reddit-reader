#!/usr/bin/env python3
"""Reddit discovery for Memojo Community, through Reddit's official API.

Runs anywhere with Python 3 and the standard library: the morning run in the
cloud, or Frank's laptop. Needs a registered Reddit app of type "script"
(https://www.reddit.com/prefs/apps) and uses the app-only token
(client_credentials), which reads public data and never acts as a person.

    python3 reddit_fetch.py --client-id ID --secret SECRET --user frankdelattin \
        --out leads.json [--days 7] [--subs googlephotos,ApplePhotos,...]

Environment variables REDDIT_CLIENT_ID, REDDIT_SECRET, REDDIT_USER work too.
Output: {"run", "fetched_at", "subreddits": {...rules...}, "leads": [...]}
with one lead per post: url, subreddit, posted, author, title, quote (<=200
chars of the post text), num_comments, score, flair, matched (the vocabulary
that matched). Nothing is posted, voted or messaged. Rate: one request per
second, far under Reddit's 100 per minute.
"""
import argparse, base64, html, json, os, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Without API credentials the script reads the public Atom feeds Reddit
# publishes for feed readers (r/<sub>/new.rss). Those carry the same posts
# with their text, author and time; what they do not carry is each
# subreddit's rules, which a card then says must be checked by hand. One
# request every three seconds; the search feeds are rate limited and skipped.
RSS_UA = "Memojo Community feed reader/0.1 (+https://memojo.eu; contact via https://memojo.eu)"
ATOM = "{http://www.w3.org/2005/Atom}"

SUBS = ["googlephotos", "ApplePhotos", "degoogle", "declutter", "digitalminimalism",
        "androidapps", "GooglePixel", "samsung", "iphone", "privacy", "photos", "ios",
        "android", "apple", "applehelp", "iphonehelp", "AndroidQuestions", "techsupport",
        "iCloud", "organization", "GalaxyS25Ultra", "Smartphones",
        "GalaxyS24Ultra", "GalaxyS23", "oneplus", "Xiaomi", "NothingTech", "fairphone",
        "PrivacyGuides", "privacytoolsIO", "fossdroid", "MacOS", "iPhoneography", "Parenting",
        "Mommit", "Genealogy", "simpleliving", "minimalism", "productivity", "ProductivityApps",
        "computerhelp", "onedrive", "dropbox", "Pixel10", "iphone17"]
# Searches run inside each subreddit (r/<sub>/search.rss, last month). Reddit's
# global search feed is rate limited; the per-subreddit one answers.
SEARCH_QUERIES = ["can't find photo", "too many photos", "organize photos", "photos app alternative"]
# What a fitting post sounds like. A post matches when any phrase appears in
# its title or text. Kept short on purpose: the run judges fit afterwards.
VOCAB = {
    "cant_find": ["can't find", "cant find", "cannot find", "can't locate", "search doesn't", "search does not",
                  "search is useless", "search sucks", "search not working", "search isn't working", "find a photo",
                  "find photos", "find the photo", "find my photos", "scrolling for", "scroll through", "lost photo",
                  "lost my photos", "photos disappeared", "photos are gone", "where are my photos", "missing photos",
                  "photos missing", "find an old photo", "find a picture", "find pictures"],
    "overwhelmed": ["too many photos", "so many photos", "thousands of photos", "000 photos", "k photos",
                    "camera roll is a mess", "camera roll mess", "organize my photos", "organise my photos",
                    "organizing photos", "organising photos", "organize photos", "organise photos",
                    "organize my pictures", "sort my photos", "sort through", "photo organization",
                    "photo organisation", "best way to organize", "how do you organize", "how do you organise",
                    "screenshots everywhere", "where do i start", "overwhelm", "declutter photos",
                    "clean up my photos", "cleaning up photos", "years of photos", "duplicate photos",
                    "duplicates", "photo mess", "backlog of photos"],
    "control": ["alternative to google photos", "google photos alternative", "alternative to icloud",
                "leave google photos", "leaving google photos", "without cloud", "no cloud", "offline gallery",
                "local gallery", "on device", "on-device", "don't want to upload", "privacy photos app",
                "gallery app recommendation", "best gallery app", "photo app recommendation"],
}
UA_FMT = "windows:eu.memojo.community:v0.1 (by /u/{user})"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"


def token(client_id, secret, ua):
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={
        "Authorization": "Basic " + auth, "User-Agent": ua,
        "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]


def get(path, tok, ua, params=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "bearer " + tok, "User-Agent": ua})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    time.sleep(1.0)
    return data


PHOTO_WORDS = ["photo", "picture", "pic ", "pics", "camera roll", "gallery", "album", "icloud photos",
               "google photos", "screenshot", "memories", "image"]


PHOTO_SUBS = {"googlephotos", "applephotos", "photos"}


def match(text, sub=""):
    """A post matches when it sounds like one of our audiences AND is about
    photos (implied in the photo subreddits); the second half keeps
    clothes-decluttering and comics readers out."""
    t = text.lower()
    if sub.lower() not in PHOTO_SUBS and not any(w in t for w in PHOTO_WORDS):
        return []
    return [k for k, phrases in VOCAB.items() if any(p in t for p in phrases)]


def lead(post, matched):
    d = post["data"]
    text = (d.get("selftext") or "").replace("\n", " ").strip()
    quote = text[:200] if text else (d.get("title") or "")[:200]
    return {
        # The run judges on `text` (up to 1500 chars); only `quote` is kept on a card.
        "text": text[:1500],
        "url": "https://www.reddit.com" + d.get("permalink", ""),
        "subreddit": "r/" + d.get("subreddit", ""),
        "posted": datetime.fromtimestamp(d.get("created_utc", 0), timezone.utc).strftime("%Y-%m-%d"),
        "author": "u/" + (d.get("author") or "unknown"),
        "title": d.get("title", ""),
        "quote": quote,
        "num_comments": d.get("num_comments", 0),
        "score": d.get("score", 0),
        "flair": d.get("link_flair_text") or "",
        "matched": matched,
        "is_self": bool(d.get("is_self")),
    }


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def rss_posts(sub, query=None):
    """One feed: the subreddit's newest posts, or a search inside it over the
    last month. Reddit meters unauthenticated readers per address and
    answers 429 with a Retry-After; we wait what it says (61 s when it says
    nothing), three times, then give up on that feed for today."""
    if query:
        url = f"https://www.reddit.com/r/{sub}/search.rss?q={urllib.parse.quote(query)}&restrict_sr=1&sort=new&t=month"
    else:
        url = f"https://www.reddit.com/r/{sub}/new.rss?limit=100"
    req = urllib.request.Request(url, headers={"User-Agent": RSS_UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                root = ET.fromstring(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 2:
                raise
            wait = e.headers.get("Retry-After")
            time.sleep(min(int(wait) if wait and wait.isdigit() else 61, 90))
    time.sleep(12.0)
    posts = []
    for e in root.findall(ATOM + "entry"):
        link = e.find(ATOM + "link")
        author = e.find(ATOM + "author/" + ATOM + "name")
        published = e.findtext(ATOM + "published") or e.findtext(ATOM + "updated") or ""
        content = strip_html(e.findtext(ATOM + "content") or "")
        # The feed's content is the post text followed by "submitted by /u/x [link] [comments]".
        content = re.sub(r"submitted by\s+/u/\S+.*$", "", content).strip()
        try:
            ts = datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
        except ValueError:
            ts = 0
        posts.append({"data": {
            "permalink": (link.get("href") if link is not None else "").replace("https://www.reddit.com", ""),
            "subreddit": sub, "created_utc": ts,
            "author": (author.text if author is not None else "unknown").replace("/u/", ""),
            "title": e.findtext(ATOM + "title") or "", "selftext": content,
            "num_comments": None, "score": None, "link_flair_text": "", "is_self": bool(content),
            "id": e.findtext(ATOM + "id") or ""}})
    return posts


def write_out(out, path):
    """Partial results after every subreddit, so a run on a deadline can use
    what is there; `complete` says whether the reader finished."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def run_rss(subs, since, out, check, searches=False, since_search=None, out_path=None, deadline=None):
    seen = set()
    out["complete"] = False
    out["subreddits_done"] = 0

    def take(posts, sub, floor):
        for post in posts:
            d = post["data"]
            if d["created_utc"] < floor or d["id"] in seen:
                continue
            m = match(d["title"] + " " + d["selftext"], sub)
            if m:
                seen.add(d["id"])
                out["leads"].append(lead(post, m))

    out["mode"] = "rss+search" if searches else "rss"
    for sub in subs:
        if deadline and time.time() > deadline:
            out.setdefault("gaps", []).append(f"time budget reached before r/{sub}; {len(subs) - out['subreddits_done']} subreddits not read")
            break
        out["subreddits"]["r/" + sub] = [{"name": "not read", "text": "rules are not in the feed; read them by hand before a Memojo mention"}]
        try:
            take(rss_posts(sub), sub, since)
        except Exception as e:
            out.setdefault("gaps", []).append(f"r/{sub} rss: {e}")
        if searches:
            limited = 0
            for q in SEARCH_QUERIES:
                if deadline and time.time() > deadline:
                    break
                try:
                    take(rss_posts(sub, q), sub, since_search or since)
                    limited = 0
                except Exception as e:
                    out.setdefault("gaps", []).append(f"r/{sub} search {q!r}: {e}")
                    if "429" in str(e):
                        limited += 1
                        if limited >= 2:  # Reddit is throttling this address: move on, the next run gets this subreddit again
                            out["gaps"].append(f"r/{sub}: searches skipped after two 429s")
                            time.sleep(30)
                            break
        out["subreddits_done"] += 1
        if out_path:
            out["leads"].sort(key=lambda l: l["posted"], reverse=True)
            write_out(out, out_path)
        if check:
            break
    else:
        out["complete"] = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", default=os.environ.get("REDDIT_CLIENT_ID"))
    ap.add_argument("--secret", default=os.environ.get("REDDIT_SECRET"))
    ap.add_argument("--user", default=os.environ.get("REDDIT_USER", "memojo"))
    ap.add_argument("--subs", default=",".join(SUBS))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--out", default="reddit_leads.json")
    ap.add_argument("--check", action="store_true", help="only one subreddit, to prove access")
    ap.add_argument("--rss", action="store_true", help="read the public feeds even if credentials exist")
    ap.add_argument("--searches", action="store_true", help="also search inside each subreddit (last month)")
    ap.add_argument("--search-days", type=int, default=30, help="how far back a search result may be")
    ap.add_argument("--shard", choices=["a", "b", "c", "d", "all"], default="all",
                    help="a to d = one quarter of the subreddits each; spreads the searches over four runs")
    ap.add_argument("--max-minutes", type=float, default=0, help="stop reading after this many minutes and write what is there")
    a = ap.parse_args()
    deadline = time.time() + a.max_minutes * 60 if a.max_minutes else None
    since = time.time() - a.days * 86400
    out = {"run": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "fetched_at": datetime.now(timezone.utc).isoformat(), "subreddits": {}, "leads": []}
    subs = [s for s in a.subs.split(",") if s]
    if a.shard != "all":
        q = (len(subs) + 3) // 4
        i = "abcd".index(a.shard)
        subs = subs[i * q:(i + 1) * q]
    if a.rss or not (a.client_id and a.secret):
        run_rss(subs, since, out, a.check, a.searches, time.time() - a.search_days * 86400, a.out, deadline)
        out["leads"].sort(key=lambda l: l["posted"], reverse=True)
        write_out(out, a.out)
        print(f"reddit_fetch ({out['mode']}): {len(out['leads'])} matching posts from {out['subreddits_done']} of {len(subs)} subreddits, "
              f"{len(out.get('gaps', []))} gaps, complete={out['complete']}, written to {a.out}")
        return
    ua = UA_FMT.format(user=a.user)
    tok = token(a.client_id, a.secret, ua)
    out["mode"] = "api"
    seen = set()
    if a.check:
        subs = subs[:1]
    for sub in subs:
        try:
            rules = get(f"/r/{sub}/about/rules", tok, ua)
            out["subreddits"]["r/" + sub] = [
                {"name": r.get("short_name", ""), "text": (r.get("description") or "")[:300]}
                for r in rules.get("rules", [])]
        except Exception as e:  # a private or quarantined subreddit answers 403; record it
            out["subreddits"]["r/" + sub] = [{"name": "unreadable", "text": str(e)[:120]}]
        try:
            listing = get(f"/r/{sub}/new", tok, ua, {"limit": 100})
        except Exception as e:
            out.setdefault("gaps", []).append(f"r/{sub}/new: {e}")
            continue
        for post in listing.get("data", {}).get("children", []):
            d = post["data"]
            if d.get("created_utc", 0) < since or d.get("id") in seen:
                continue
            m = match((d.get("title") or "") + " " + (d.get("selftext") or ""), sub)
            if m:
                seen.add(d["id"])
                out["leads"].append(lead(post, m))
        if a.check:
            break
    if not a.check:
        # Global search, newest first, for the phrases people use outside our subreddits.
        for q in ["can't find photo", "too many photos", "organize photos phone",
                  "alternative to google photos", "gallery app no cloud", "camera roll mess"]:
            try:
                res = get("/search", tok, ua, {"q": q, "sort": "new", "t": "week", "limit": 50, "type": "link"})
            except Exception as e:
                out.setdefault("gaps", []).append(f"search {q!r}: {e}")
                continue
            for post in res.get("data", {}).get("children", []):
                d = post["data"]
                if d.get("created_utc", 0) < since or d.get("id") in seen or d.get("over_18"):
                    continue
                m = match((d.get("title") or "") + " " + (d.get("selftext") or ""))
                if m:
                    seen.add(d["id"])
                    out["leads"].append(lead(post, m))
    out["leads"].sort(key=lambda l: l["posted"], reverse=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"reddit_fetch: {len(out['leads'])} matching posts from {len(subs)} subreddits, "
          f"{len(out.get('gaps', []))} gaps, written to {a.out}")


if __name__ == "__main__":
    main()
