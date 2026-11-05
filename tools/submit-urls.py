#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署完成后，把「最近改动过的文章」推给百度和必应（IndexNow）。

为什么需要这个脚本：
  搜索引擎抓取靠两条路 —— 自己去爬（慢，新站尤其慢），或者你告诉它（快）。
  这个脚本做第二条：
    · 百度主动推送：POST 到 data.zz.baidu.com，配额很小（新站 10 条/天），
      所以只推 sitemap 里 lastmod 最近的那几篇；
    · IndexNow：必应（以及 Yandex、Seznam 等）共享的即时推送协议，
      配额宽松，一次推 100 条也没问题。

为什么从 sitemap 取 URL 而不是从 content/ 目录推：
  文章的最终 URL 由 permalinks.toml 决定，还可能被 slug / url 前置字段改写，
  自己拼路径迟早拼错。站点刚发布完，sitemap 就是最准的 URL 清单。

用法：
  python3 tools/submit-urls.py --dry-run     # 只打印将要推的 URL，不发请求
  python3 tools/submit-urls.py               # 正常推送（CI 里就是这样跑的）
  PUSH_ALL=1 python3 tools/submit-urls.py    # 忽略时间窗口，推全部文章（首次收录用）

环境变量：
  BAIDU_TOKEN     百度主动推送的 token，没设就跳过百度（GitHub Secrets 里配）
  INDEXNOW_KEY    IndexNow 的 key，没设就自动从 static/ 目录里找（文件名=key，内容=key）
  RECENT_DAYS     时间窗口，默认 7 天
  BAIDU_LIMIT     单次最多推几条给百度，默认 10（跟着配额走）
  INDEXNOW_LIMIT  单次最多推几条给 IndexNow，默认 100
  PUSH_ALL        设为 1 时忽略时间窗口
  SITE_URL        站点地址，默认 https://2019527.xyz
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

SITE = os.environ.get("SITE_URL", "https://2019527.xyz").rstrip("/")
SITEMAP = f"{SITE}/sitemap.xml"
POSTS_PREFIX = f"{SITE}/posts/"

RECENT_DAYS = int(os.environ.get("RECENT_DAYS", "7"))
BAIDU_LIMIT = int(os.environ.get("BAIDU_LIMIT", "10"))
INDEXNOW_LIMIT = int(os.environ.get("INDEXNOW_LIMIT", "100"))
PUSH_ALL = os.environ.get("PUSH_ALL", "") in ("1", "true", "True", "yes")

BAIDU_TOKEN = os.environ.get("BAIDU_TOKEN", "").strip()
BAIDU_ENDPOINT = "http://data.zz.baidu.com/urls"

UA = "Mozilla/5.0 (compatible; 2019527.xyz-submit/1.0)"


def log(msg):
    print(msg, flush=True)


def http(url, data=None, headers=None, timeout=30, method=None):
    """极简 HTTP 封装，返回 (状态码, 响应体文本)。4xx/5xx 不抛异常，交给调用方判断。"""
    hdrs = {"User-Agent": UA}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # 网络层错误（DNS / TLS / 超时）
        return 0, f"{type(e).__name__}: {e}"


def fetch_sitemap(retries=3):
    """
    取站点 sitemap。刚部署完 CDN 可能有几秒到几十秒的延迟，
    所以失败要重试，不能一失败就放弃（那样这次推送就白跑了）。
    """
    last_err = ""
    for i in range(retries):
        url = f"{SITEMAP}?t={int(time.time())}"  # 加时间戳绕开缓存
        status, body = http(url)
        if status == 200 and ("<urlset" in body or "<sitemapindex" in body):
            return body
        last_err = f"HTTP {status} {body[:120]}"
        log(f"  取 sitemap 失败（第 {i + 1}/{retries} 次）：{last_err}")
        time.sleep(5)
    raise SystemExit(f"sitemap 取不到，放弃本次推送：{last_err}")


def parse_entries(xml_text):
    """解析 sitemap，返回 [(url, lastmod_datetime|None)]。"""
    root = ET.fromstring(xml_text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries = []
    for node in root.findall("sm:url", ns):
        loc = node.findtext("sm:loc", default="", namespaces=ns).strip()
        if not loc:
            continue
        raw = node.findtext("sm:lastmod", default="", namespaces=ns).strip()
        when = None
        if raw:
            try:
                when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
            except ValueError:
                when = None
        entries.append((loc, when))
    return entries


def find_indexnow_key():
    """
    IndexNow 的 key 必须放在站点根目录：https://站点/<key>.txt，文件内容就是 key 本身。
    这里从 static/ 里找那个 32 位十六进制命名的 txt，省得再配一个变量。
    """
    env_key = os.environ.get("INDEXNOW_KEY", "").strip()
    if env_key:
        return env_key
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
    if not os.path.isdir(static_dir):
        return ""
    for name in os.listdir(static_dir):
        if re.fullmatch(r"[0-9a-f]{32}\.txt", name):
            return name[:-4]
    return ""


def post_baidu(urls):
    """百度主动推送。返回 (是否成功, 说明)。"""
    if not BAIDU_TOKEN:
        return False, "没配 BAIDU_TOKEN，跳过"
    endpoint = f"{BAIDU_ENDPOINT}?site={urllib.parse.quote(SITE, safe=':/')}&token={BAIDU_TOKEN}"
    body = "\n".join(urls).encode("utf-8")
    status, text = http(endpoint, data=body, headers={"Content-Type": "text/plain"})
    log(f"  百度返回 HTTP {status}：{text.strip()[:400]}")
    # 百度成功时返回 {"success":n,"remain":m}；失败是 {"error":..,"message":..}
    try:
        data = json.loads(text)
    except Exception:
        return False, f"响应无法解析：{text[:120]}"
    if "success" in data:
        return True, f"成功 {data.get('success')} 条，今日剩余配额 {data.get('remain')}"
    return False, f"error={data.get('error')} {data.get('message', '')}"


def post_indexnow(urls, key):
    """IndexNow 推送（必应 / Yandex / Seznam 共用）。"""
    if not key:
        return False, "没找到 IndexNow key（static/ 下少了 <key>.txt）"
    payload = {
        "host": SITE.split("//", 1)[-1],
        "key": key,
        "keyLocation": f"{SITE}/{key}.txt",
        "urlList": urls,
    }
    status, text = http(
        "https://api.indexnow.org/indexnow",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    log(f"  IndexNow 返回 HTTP {status}：{text.strip()[:400] or '(空响应，200/202 即为成功)'}")
    return status in (200, 202), f"HTTP {status}"


def main():
    dry_run = "--dry-run" in sys.argv
    log(f"站点：{SITE}")

    entries = parse_entries(fetch_sitemap())
    log(f"sitemap 共 {len(entries)} 条 URL")

    # 只推文章。列表页、分类页、标签页没必要占配额。
    posts = [(u, w) for u, w in entries if u.startswith(POSTS_PREFIX) and u.rstrip("/") != POSTS_PREFIX.rstrip("/")]
    log(f"其中文章 {len(posts)} 篇")

    if not PUSH_ALL:
        cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
        recent = [(u, w) for u, w in posts if w and w >= cutoff]
        log(f"最近 {RECENT_DAYS} 天有改动：{len(recent)} 篇（改 PUSH_ALL=1 可推全部）")
        posts = recent
    else:
        log("PUSH_ALL=1：推全部文章")

    if not posts:
        log("没有需要推送的 URL，结束。")
        return 0

    # 新的在前。lastmod 缺失的排最后。
    posts.sort(key=lambda x: x[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    urls = [u for u, _ in posts]

    baidu_urls = urls[:BAIDU_LIMIT]
    indexnow_urls = urls[:INDEXNOW_LIMIT]

    log(f"准备推给百度 {len(baidu_urls)} 条、IndexNow {len(indexnow_urls)} 条")
    for u in baidu_urls:
        log(f"  · {u}")

    if dry_run:
        log("--dry-run：只打印，不发请求。")
        return 0

    ok_baidu, msg_baidu = post_baidu(baidu_urls)
    log(f"百度：{'✅' if ok_baidu else '⚠️'} {msg_baidu}")

    ok_in, msg_in = post_indexnow(indexnow_urls, find_indexnow_key())
    log(f"IndexNow：{'✅' if ok_in else '⚠️'} {msg_in}")

    # 搜索引擎抽风不该让流水线变红：站点已经发布成功了，推送只是锦上添花。
    if not ok_baidu and not ok_in:
        log("两个渠道都没成功，但站点已发布，不算失败。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
