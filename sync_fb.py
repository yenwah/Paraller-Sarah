#!/usr/bin/env python3
"""
Facebook Viral Sync — Supabase edition
---------------------------------------
Same idea as sync_content.py (Instagram), but for Facebook 专页 (Pages):

  1. read active FB competitors from the Supabase `competitors` table
     (tracker = 'FB'; username = 专页名 like `katacaremy`, or the full page URL)
  2. Apify `facebook-pages-scraper`  -> follower count per page
  3. Apify `facebook-posts-scraper`  -> recent posts (reactions / comments / shares)
  4. keep the standout posts, UPSERT into the `posts` table with tracker = 'FB'

A post is kept when it clears a small noise floor AND passes ANY of three tests
(engagement rate, comment count, or X times that page's own median) -- exactly
like the IG sync. Every page also contributes its TOP_N best posts so a quiet
week still fills the board.

Facebook differences worth knowing:
  * `likes` stores TOTAL REACTIONS (all emoji reactions), `shares` is new and is
    the strongest "people want to spread this" signal on Facebook.
  * Facebook pages have lower engagement rates than IG, so the default
    thresholds below are lower than the IG ones.
  * Facebook video links are usually not downloadable, so most FB posts are
    analysed from their caption text (that is fine: FB is text-first).

Env (required): APIFY_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
                TRACKER=FB (set by the workflow)
Env (tuning, all optional -- GitHub Actions *Variables*):
     FB_MIN_ER (0.005)  FB_MIN_COMMENTS (8)  FB_MIN_ENGAGE (10)  FB_OUTLIER_X (1.5)
     FB_TOP_N_PER_COMP (3)  FB_MAX_PER_COMP (15)  FB_DAYS_BACK (90)
     FB_RESULTS_LIMIT (30)  <- only this one changes the Apify bill
"""

import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timezone

os.environ.setdefault("TRACKER", "FB")
os.environ["TRACKER"] = "FB"  # this script only ever writes FB rows

from sync_content import _envf, _envi, _request, cleanup, run_actor, sb  # noqa: E402

TRACKER = "FB"

MIN_ER = _envf("FB_MIN_ER", 0.005)
MIN_COMMENTS = _envi("FB_MIN_COMMENTS", 8)
MIN_ENGAGE = _envi("FB_MIN_ENGAGE", 10)
OUTLIER_X = _envf("FB_OUTLIER_X", 1.5)
TOP_N_PER_COMP = _envi("FB_TOP_N_PER_COMP", 3)
MAX_PER_COMP = _envi("FB_MAX_PER_COMP", 15)
DAYS_BACK = _envi("FB_DAYS_BACK", 90)
RESULTS_LIMIT = _envi("FB_RESULTS_LIMIT", 30)

PAGES_ACTOR = os.environ.get("FB_PAGES_ACTOR") or "apify~facebook-pages-scraper"
POSTS_ACTOR = os.environ.get("FB_POSTS_ACTOR") or "apify~facebook-posts-scraper"


# ---------------------------------------------------------------------------
# Page handles
# ---------------------------------------------------------------------------


def handle_of(value):
    """'https://www.facebook.com/KataCareMY/?ref=x' -> 'katacaremy'.
    Plain names pass through. Returns '' when it is not a page reference."""
    n = (value or "").strip()
    if not n:
        return ""
    if "facebook.com" in n or "fb.com" in n or "fb.me" in n:
        u = urllib.parse.urlparse(n if "//" in n else "https://" + n)
        parts = [p for p in u.path.split("/") if p]
        if parts and parts[0] == "profile.php":
            n = (urllib.parse.parse_qs(u.query).get("id") or [""])[0]
        elif parts and parts[0] == "pages" and len(parts) >= 2:
            n = parts[-1]
        elif parts:
            n = parts[0]
        else:
            return ""
    return n.lstrip("@").strip().strip("/").lower()


def start_url(value):
    """Page URL we hand to Apify."""
    n = (value or "").strip()
    if "facebook.com" in n:
        u = urllib.parse.urlparse(n if "//" in n else "https://" + n)
        parts = [p for p in u.path.split("/") if p]
        if parts and parts[0] == "profile.php":
            return "https://www.facebook.com/profile.php?id=" + (
                urllib.parse.parse_qs(u.query).get("id") or [""])[0]
        if parts and parts[0] == "pages":
            return "https://www.facebook.com/" + "/".join(parts)
        if parts:
            return "https://www.facebook.com/" + parts[0]
    h = handle_of(n)
    return ("https://www.facebook.com/" + h) if h else ""


def fetch_competitors():
    rows = sb(f"competitors?select=username&tracker=eq.{TRACKER}&active=is.true")
    pages, seen = [], set()
    for r in rows:
        raw = (r.get("username") or "").strip()
        h, url = handle_of(raw), start_url(raw)
        if not h or not url:
            print(f"  WARNING: skipping unusable FB competitor: {raw[:60]!r}")
            continue
        if h in seen:
            continue
        seen.add(h)
        pages.append({"handle": h, "url": url})
    return pages


def squash(s):
    return re.sub(r"[^a-z0-9一-鿿]", "", (s or "").lower())


# ---------------------------------------------------------------------------
# Reading Apify items (field names differ a little between actor versions,
# so every lookup tries several spellings)
# ---------------------------------------------------------------------------


def first(d, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def to_int(v):
    try:
        if isinstance(v, str):
            v = v.replace(",", "").strip()
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse_date(v):
    if isinstance(v, (int, float)):
        if v > 1e12:  # milliseconds
            v = v / 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc).date().isoformat()
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return None


def resolve_handle(item, wanted, name_to_handle):
    """Which of OUR competitor pages does this scraped item belong to?"""
    cands = [item.get(k) for k in ("facebookUrl", "pageUrl", "topLevelUrl", "inputUrl", "url")]
    user = item.get("user") or item.get("page") or {}
    if isinstance(user, dict):
        cands += [user.get("profileUrl"), user.get("url")]
    for c in cands:
        h = handle_of(c) if isinstance(c, str) else ""
        if h in wanted:
            return h
    nm = squash(first(item, "pageName", "title", "name", default="") or
                (user.get("name") if isinstance(user, dict) else "") or "")
    if nm and nm in name_to_handle:
        return name_to_handle[nm]
    return ""


def media_list(item):
    m = item.get("media")
    return m if isinstance(m, list) else []


def post_kind(item):
    media = media_list(item)
    types = " ".join(str(x.get("__typename") or x.get("type") or "") for x in media if isinstance(x, dict)).lower()
    url = str(first(item, "url", "postUrl", default="")).lower()
    if "video" in types or "reel" in types or "/videos/" in url or "/reel/" in url or item.get("isVideo"):
        return "Video"
    if len(media) > 1:
        return "Carousel"
    if media:
        return "Image"
    return "Text"


def video_url(item):
    v = first(item, "videoUrl", "video_url", "videoSdUrl", "videoHdUrl")
    if isinstance(v, str) and v.startswith("http"):
        return v
    for x in media_list(item):
        if isinstance(x, dict):
            for k in ("video_url", "videoUrl", "playable_url", "playableUrl", "sd_src", "hd_src"):
                if isinstance(x.get(k), str) and x[k].startswith("http"):
                    return x[k]
    return None


def thumbnail(item):
    t = first(item, "thumbnail", "thumbnailUrl", "imageUrl", "image")
    if isinstance(t, str) and t.startswith("http"):
        return t
    for x in media_list(item):
        if isinstance(x, dict):
            for k in ("thumbnail", "photo_image", "image", "url"):
                v = x.get(k)
                if isinstance(v, dict):
                    v = v.get("uri") or v.get("url")
                if isinstance(v, str) and v.startswith("http"):
                    return v
    return None


def hashtags(text):
    tags = re.findall(r"#([^\s#,.!?:;]+)", text or "")
    return ", ".join(dict.fromkeys(tags))


def post_id_of(item):
    pid = str(first(item, "postId", "post_id", "id", default="") or "").strip()
    if not pid:
        m = re.search(r"(\d{8,})", str(first(item, "url", "postUrl", default="")))
        pid = m.group(1) if m else ""
    return ("fb_" + pid) if pid else ""


# ---------------------------------------------------------------------------
# Transform
# ---------------------------------------------------------------------------


def to_rows(items, followers_map, wanted, name_to_handle, today):
    by_comp, nofol, broken, unmatched = {}, 0, 0, 0
    for it in items:
        if not isinstance(it, dict) or it.get("error"):
            broken += 1
            continue
        pid = post_id_of(it)
        if not pid:
            broken += 1
            continue
        h = resolve_handle(it, wanted, name_to_handle)
        if not h:
            unmatched += 1
            continue
        fol = followers_map.get(h, 0)
        if not fol:
            nofol += 1
            continue
        likes = to_int(first(it, "likes", "reactionsCount", "reactions", default=0)
                       if not isinstance(it.get("reactions"), dict) else it["reactions"].get("total"))
        comments = to_int(first(it, "comments", "commentsCount", default=0))
        shares = to_int(first(it, "shares", "sharesCount", default=0))
        text = (first(it, "text", "message", "caption", default="") or "")
        kind = post_kind(it)
        link = first(it, "url", "postUrl", "topLevelUrl", default="") or ""
        by_comp.setdefault(h, []).append({
            "row": {
                "post_id": pid,
                "tracker": TRACKER,
                "competitor": h,
                "caption": str(text)[:5000],
                "post_type": kind,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "followers": fol,
                "post_date": parse_date(first(it, "time", "timestamp", "date")),
                "post_url": link,
                "thumbnail_url": thumbnail(it),
                "video_url": video_url(it),
                "hashtags": hashtags(str(text)),
                "is_video": kind == "Video",
                "last_synced": today,
            },
            "eng": likes + comments,
            "er": (likes + comments) / fol,
            "comments": comments,
            "score": (likes + comments * 3) / fol * 100,  # same as the DB viral_score
        })

    rows, below_total, rescued_total = [], 0, 0
    print(f"  {'专页':<26}{'抓到':>5}{'入选':>5}{'补位':>5}  基准/中位互动")
    for h in sorted(by_comp):
        recs = by_comp[h]
        engs = [r["eng"] for r in recs]
        med = statistics.median(engs) if len(engs) >= 3 else 0
        keep_ids, kept = set(), []
        for r in recs:
            if r["eng"] < MIN_ENGAGE:
                continue
            if (r["er"] >= MIN_ER or r["comments"] >= MIN_COMMENTS
                    or (med > 0 and r["eng"] >= OUTLIER_X * med)):
                keep_ids.add(r["row"]["post_id"])
                kept.append(r)
        passed = len(kept)
        rescued = 0
        if passed < TOP_N_PER_COMP:
            for r in sorted(recs, key=lambda r: -r["score"]):
                if r["row"]["post_id"] in keep_ids:
                    continue
                keep_ids.add(r["row"]["post_id"])
                kept.append(r)
                rescued += 1
                if len(kept) >= TOP_N_PER_COMP:
                    break
        capped = 0
        if len(kept) > MAX_PER_COMP:
            kept.sort(key=lambda r: -r["score"])
            capped = len(kept) - MAX_PER_COMP
            kept = kept[:MAX_PER_COMP]
        below_total += len(recs) - passed
        rescued_total += rescued
        rows.extend(r["row"] for r in kept)
        note = f" · 超额截掉 {capped}" if capped else ""
        print(f"  {h:<26}{len(recs):>5}{len(kept):>5}{rescued:>5}  "
              f"中位 {int(med)} 互动 · {recs[0]['row']['followers']:,} 粉{note}")

    print(f"  -- 合计 {len(rows)} 条入库 ({len(rows) - rescued_total} 达标 + {rescued_total} 补位) | "
          f"{below_total} 条未达标 | {nofol} 条缺粉丝数 | {unmatched} 条对不上专页 | {broken} 条抓取失败")
    if unmatched:
        print("  提示: 「对不上专页」= 抓回来的贴文认不出是哪个竞对。看上面 [Debug] 打印的字段名,")
        print("        再确认 competitors 表里 FB 的 Username 就是专页网址里 facebook.com/ 后面那一段。")
    if len(rows) < 15:
        print("  提示: 内容偏少。到仓库 Settings → Variables 调松阈值,例如")
        print("        FB_MIN_ER=0.003  FB_MIN_COMMENTS=4  FB_TOP_N_PER_COMP=5  FB_DAYS_BACK=120")
        print("        或在 Supabase 的 competitors 表多加几个 tracker=FB 的专页。")
    return rows


def upsert(rows):
    """Write in chunks. If the `shares` column is missing (fb-setup.sql not run
    yet), retry without it so the posts still land."""
    use_shares = True
    for i in range(0, len(rows), 100):
        chunk = rows[i:i + 100]
        while True:
            body = chunk if use_shares else [{k: v for k, v in r.items() if k != "shares"} for r in chunk]
            try:
                sb("posts?on_conflict=post_id", method="POST", data=body,
                   prefer="resolution=merge-duplicates,return=minimal")
                break
            except urllib.error.HTTPError as exc:
                if use_shares and exc.code in (400, 404):
                    print("  posts 表还没有 shares 这一列 -> 这次先不存转发数。")
                    print("  补上只要一句:Supabase → SQL Editor → 贴 fb-setup.sql 第 1 段 → Run")
                    use_shares = False
                    continue
                raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    token = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not token or not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("ERROR: APIFY_TOKEN / SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY required")
        sys.exit(1)

    pages = fetch_competitors()
    if not pages:
        print("No active FB competitors in Supabase (competitors 表里 tracker=FB 且 active 打勾) — nothing to do.")
        print("先跑 fb-setup.sql 第 2 段把同行名单放进去。")
        return
    wanted = {p["handle"] for p in pages}
    urls = [{"url": p["url"]} for p in pages]
    print(f"[FB] {len(pages)} pages: {', '.join(p['handle'] for p in pages[:8])}"
          + (" ..." if len(pages) > 8 else ""))
    print(f"  filter: ER>={MIN_ER:.2%} OR comments>={MIN_COMMENTS} OR "
          f"engagements>={OUTLIER_X}x own median | floor {MIN_ENGAGE} | "
          f"keep {TOP_N_PER_COMP}-{MAX_PER_COMP} per page")

    profiles = run_actor(token, PAGES_ACTOR, {"startUrls": urls}, "Step 1 pages")
    followers, name_to_handle = {}, {}
    for pr in profiles:
        if not isinstance(pr, dict):
            continue
        h = ""
        for k in ("facebookUrl", "pageUrl", "url", "inputUrl"):
            hh = handle_of(pr.get(k)) if isinstance(pr.get(k), str) else ""
            if hh in wanted:
                h = hh
                break
        nm = squash(first(pr, "pageName", "title", "name", default=""))
        if not h and nm:
            for w in wanted:
                if squash(w) == nm:
                    h = w
                    break
        if not h:
            continue
        if nm:
            name_to_handle[nm] = h
        c = to_int(first(pr, "followers", "followersCount", "likes", "pageLikes", default=0))
        if c:
            followers[h] = c
    print(f"  followers for {len(followers)}/{len(pages)} pages")
    missing = sorted(wanted - set(followers))
    if missing:
        print("  WARNING: 没拿到粉丝数(这些专页会被跳过,多半是网址不对或专页不公开): " + ", ".join(missing))
    if profiles and isinstance(profiles[0], dict):
        print("  [Debug] pages 字段: " + ", ".join(sorted(profiles[0].keys())[:25]))

    items = run_actor(token, POSTS_ACTOR,
                      {"startUrls": urls, "resultsLimit": RESULTS_LIMIT,
                       "onlyPostsNewerThan": f"{DAYS_BACK} days"}, "Step 2 posts")
    print(f"  scraped {len(items)} posts (last {DAYS_BACK} days, <= {RESULTS_LIMIT}/page)")
    if items and isinstance(items[0], dict):
        print("  [Debug] posts 字段: " + ", ".join(sorted(items[0].keys())[:30]))

    today = datetime.now(timezone.utc).date().isoformat()
    rows = to_rows(items, followers, wanted, name_to_handle, today)
    if rows:
        upsert(rows)
        print(f"[Upsert] {len(rows)} rows written")
    else:
        print("[Upsert] nothing passed the filter — check the per-page table above, "
              "then loosen the FB_ Variables or add more pages")

    try:
        cleanup()
    except Exception as exc:
        print(f"[Cleanup] skipped ({exc})")
    print("Done.")


if __name__ == "__main__":
    main()
