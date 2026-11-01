#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取本站每篇文章的阅读量，生成 data/pv.json，供首页「热门文章」板块使用。

为什么要有这个脚本
------------------
本站用 vercount（不蒜子兼容）计数，它只提供「按网址查单篇阅读量」的接口，
没有排行榜接口。所以要自己把每篇文章查一遍、排个序。

为什么不放在 Hugo 模板里查
--------------------------
Hugo 的 resources.GetRemote 是串行请求，55 篇文章约 3 分钟，会把构建拖垮；
这里用 6 个线程并发，25 秒左右跑完。脚本失败不影响构建（见 deploy.yml 的
continue-on-error），失败时不写文件，页面上的板块自动隐藏，不会显示错数据。

接口说明
--------
GET https://events.vercount.one/api/v2/log?url=<完整网址>
  → {"status":"success","data":{"site_pv":309,"page_pv":13}}
这是**只读**接口，不会给文章凭空加一次阅读量（POST 才是计数）。
必须带浏览器 User-Agent，否则返回 403。
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://events.vercount.one/api/v2/log?url="
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def site_base():
    """从生产环境配置里取 baseURL，保证抓的地址和线上一致。"""
    for rel in ("config/production/hugo.toml", "config/_default/hugo.toml"):
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            m = re.search(r'^\s*baseURL\s*=\s*["\']([^"\']+)', f.read(), re.M)
        if m:
            return m.group(1).rstrip("/")
    return "https://2019527.xyz"


def post_dirs():
    """content/posts 下每个子目录就是一篇文章，目录名即网址路径。"""
    base = os.path.join(ROOT, "content", "posts")
    dirs = [d for d in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, d))]
    return [d for d in dirs if os.path.exists(os.path.join(base, d, "index.md"))]


def fetch(base, name):
    url = "%s/posts/%s/" % (base, name)
    req = urllib.request.Request(
        API + urllib.parse.quote(url, safe=""),
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read().decode("utf-8"))
            return name, int(data.get("data", {}).get("page_pv") or 0), None
        except Exception as e:  # 超时 / 403 / 接口抽风，重试一次再放弃
            if attempt == 1:
                return name, 0, "%s: %s" % (name, e)
            time.sleep(0.8)
    return name, 0, None


def main():
    base = site_base()
    names = post_dirs()
    if not names:
        print("没有找到文章，跳过")
        return 0

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda n: fetch(base, n), names))

    pages = {"/posts/%s/" % n: pv for n, pv, _ in results}
    errors = [e for _, _, e in results if e]
    nonzero = sum(1 for pv in pages.values() if pv > 0)

    print("共 %d 篇，耗时 %.1fs，有阅读量 %d 篇，失败 %d 篇"
          % (len(names), time.time() - t0, nonzero, len(errors)))
    for e in errors[:5]:
        print("  ! " + e)

    # 全军覆没多半是接口挂了：这次不写文件，保留上一次的数据（板块宁可不更新，也不能清零）
    if errors and nonzero == 0:
        print("接口异常，本次不更新 data/pv.json")
        return 0

    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total": sum(pages.values()),
        "pages": pages,
    }
    dest = os.path.join(ROOT, "data", "pv.json")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("已写入 %s" % dest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
