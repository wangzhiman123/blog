#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Hugo 文章图片本地化备份工具
============================

把文章里引用的网络图片下载到 index.md 同目录，并把链接改写成相对引用，
这样图片就跟着文章一起进了 Git 仓库，不再怕图床跑路 / CDN 防盗链。

用法（最省事的方式：双击同目录的「图片备份工具.bat」）：

    python backup_images.py                 # 处理上一级目录下所有 index.md
    python backup_images.py D:\blog\content # 指定要扫描的目录
    python backup_images.py --dry-run       # 只预览，不改任何文件
    python backup_images.py --help          # 看全部参数

只依赖 Python 标准库，不需要 pip install 任何东西。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

VERSION = "1.2.1"

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(TOOL_DIR, "_reports")
MANIFEST_PATH = os.path.join(TOOL_DIR, "_manifest.json")


def _detect_default_root() -> str:
    """工具放在哪都能用：从上一级开始往上找，第一个含 index.md 的目录就是默认扫描范围。"""
    current = os.path.dirname(TOOL_DIR)
    for _ in range(4):
        try:
            for _, dirnames, filenames in os.walk(current):
                dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "_reports"]
                if "index.md" in filenames:
                    return current
        except OSError:
            pass
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.dirname(TOOL_DIR)


DEFAULT_ROOT = _detect_default_root()

# ---------------------------------------------------------------- 可调参数 ----

# 假装成一个浏览器，避免被图床当成爬虫拦掉
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    # 注意：千万别写 image/webp 之类的格式偏好，很多 CDN 会据此现场转码，
    # 拿回来的就不是原图了（实测 png 原图 95KB 会被换成 26KB 的 webp）。
    "Accept": "image/*,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MAX_IMAGE_BYTES = 40 * 1024 * 1024   # 单张图超过 40MB 就不要了，多半是错的响应
TIMEOUT = 30                         # 单次请求超时（秒）
RETRIES = 3                          # 每个地址重试次数（不含首次）

# 这些查询参数只是让 CDN 现场压缩/裁剪，留着会拿到模糊的缩略图，
# 所以默认剥掉它们去取原图；剥掉后要是 403/404，会自动退回原始地址。
IMAGE_PROCESS_PARAMS = (
    "x-oss-process",
    "x-oss-image",
    "imageView2",
    "imageMogr2",
    "imageslim",
    "thumbnail",
    "watermark",
    "resize",
    "w",
    "h",
    "q",
    "quality",
    "format",
    "width",
    "height",
)

# front matter 里可能是图片的字段名（小写比较）
FRONT_MATTER_IMAGE_FIELDS = (
    "featured_image_preview",
    "featured_image",
    "feature_image",
    "featureimage",
    "image",
    "images",
    "cover",
    "thumbnail",
    "banner",
    "preview",
)

BACKUP_SUFFIX = ".index.md.bak"      # 以点开头，Hugo 会自动忽略

# ------------------------------------------------------------------ 正则 ----

# ![alt](url "title")
MD_IMAGE_RE = re.compile(
    r"""!\[(?P<alt>[^\]\n]*)\]\(
        \s*
        (?P<url><[^>\n]*>|[^)\s]+)
        (?P<title>\s+(?:"[^"\n]*"|'[^'\n]*'))?
        \s*\)
    """,
    re.VERBOSE,
)

HTML_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
HTML_SRC_RE = re.compile(r"""(\bsrc\s*=\s*)(["'])(?P<url>[^"']*)\2""", re.IGNORECASE)

FENCE_RE = re.compile(r"^(?P<indent>\s{0,3})(?P<fence>`{3,}|~{3,})")
FM_DELIM_RE = re.compile(r"^---\s*$")

BARE_URL_RE = re.compile(r"""https?://[^\s"'<>)\]，。；]+""", re.IGNORECASE)
IMG_EXT_RE = re.compile(r"\.(jpe?g|png|gif|webp|svg|bmp|avif|tiff?|ico)$", re.IGNORECASE)

# --------------------------------------------------------------- 数据模型 ----


@dataclass
class ImageRef:
    """文章里出现的一处图片引用。"""
    url: str            # 原始写法（可能是 // 开头、带 query）
    key: str            # 规范化后的 key，用来去重
    kind: str           # 'md' | 'html' | 'frontmatter'


@dataclass
class DownloadResult:
    key: str
    ok: bool
    filename: str = ""
    size: int = 0
    source: str = ""
    error: str = ""
    from_cache: bool = False


@dataclass
class ArticleStats:
    path: str
    total_refs: int = 0
    remote_refs: int = 0
    local_refs: int = 0
    downloaded: int = 0
    reused: int = 0
    failed: int = 0
    rewritten: int = 0
    missing_local: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    changed: bool = False


# ------------------------------------------------------------------ 工具 ----


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f}{unit}" if unit == "B" else f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}GB"


def is_remote(url: str) -> bool:
    u = url.strip().lower()
    if u.startswith("//"):
        return True
    return u.startswith("http://") or u.startswith("https://")


def normalize_url(url: str) -> str:
    """把 //xxx 补成 https://xxx，并去掉首尾空白和 < >"""
    u = url.strip().strip("<>").strip()
    if u.startswith("//"):
        u = "https:" + u
    return u


def strip_process_params(url: str) -> str:
    """去掉 CDN 的图片处理参数，尽量拿原图。"""
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return url
    kept = []
    for part in parsed.query.split("&"):
        if not part:
            continue
        name = part.split("=", 1)[0]
        if name.lower() in IMAGE_PROCESS_PARAMS:
            continue
        kept.append(part)
    new_query = "&".join(kept)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, new_query, parsed.fragment)
    )


def url_key(url: str) -> str:
    """同一张图的不同写法（带不带处理参数）算同一个 key。"""
    u = normalize_url(url)
    return strip_process_params(u).split("#", 1)[0]


def sniff_ext(data: bytes) -> str | None:
    """看文件头猜真实格式，比 URL 后缀靠谱。"""
    if len(data) < 12:
        return None
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"BM":
        return ".bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tif"
    if data[:4] == b"\x00\x00\x01\x00":
        return ".ico"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"avif", b"avis"):
            return ".avif"
        if brand in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
            return ".heic"
    head = data[:600].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return ".svg"
    return None


def ext_from_content_type(ctype: str) -> str | None:
    ctype = (ctype or "").split(";")[0].strip().lower()
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/pjpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/svg+xml": ".svg",
        "image/bmp": ".bmp",
        "image/x-ms-bmp": ".bmp",
        "image/avif": ".avif",
        "image/heic": ".heic",
        "image/heif": ".heic",
        "image/tiff": ".tif",
        "image/x-icon": ".ico",
        "image/vnd.microsoft.icon": ".ico",
    }.get(ctype)


def sanitize_filename(name: str) -> str:
    """把名字弄成 Windows / macOS / Linux 都能存的样子。"""
    name = urllib.parse.unquote(name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "-", name)
    name = name.strip(" .")
    if not name:
        name = "image"
    if len(name) > 100:
        stem, ext = os.path.splitext(name)
        name = stem[:90] + ext
    return name


def make_filename(url: str, ext: str) -> str:
    """用 URL 里的文件名，保证同一张图名字稳定。"""
    parsed = urllib.parse.urlsplit(url)
    base = os.path.basename(parsed.path) or ""
    base = sanitize_filename(base)
    stem, old_ext = os.path.splitext(base)
    if not stem or re.fullmatch(r"[0-9a-fA-F\-_]{16,}", stem):
        # 纯 hash 名字保留原样即可，它本身就是唯一的
        pass
    if not stem:
        stem = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    if IMG_EXT_RE.match(old_ext) and old_ext.lower() == ext.lower():
        return f"{stem}{ext}"
    # 后缀和真实格式不一致（比如 .jpeg 实际是 webp），以真实格式为准
    return f"{stem}{ext}"


# --------------------------------------------------------- 请求与下载逻辑 ----


class Downloader:
    def __init__(self, keep_query: bool = False, referer: str = "", workers: int = 6):
        self.keep_query = keep_query
        self.referer = referer
        self._mem_cache: dict[str, tuple[bytes, str]] = {}
        self._cache_bytes = 0
        self._lock = threading.Lock()
        self._local = threading.local()

    def _opener(self):
        opener = getattr(self._local, "opener", None)
        if opener is None:
            opener = urllib.request.build_opener()
            self._local.opener = opener
        return opener

    def _fetch_once(self, url: str) -> tuple[bytes, str]:
        headers = dict(HTTP_HEADERS)
        if self.referer:
            headers["Referer"] = self.referer
        else:
            parsed = urllib.parse.urlsplit(url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        req = urllib.request.Request(url, headers=headers)
        with self._opener().open(req, timeout=TIMEOUT) as resp:
            ctype = resp.headers.get("Content-Type", "")
            data = resp.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"文件超过 {human_size(MAX_IMAGE_BYTES)}，疑似异常响应")
        if not data:
            raise ValueError("服务器返回空内容")
        return data, ctype

    def _fetch_with_retry(self, url: str) -> tuple[bytes, str]:
        last: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                return self._fetch_once(url)
            except urllib.error.HTTPError as exc:
                last = exc
                if exc.code in (401, 403, 404, 410):
                    break  # 这类错误重试也没用，交给上层换地址
                if attempt < RETRIES:
                    time.sleep(1.5 * (attempt + 1))
            except Exception as exc:  # 网络抖动、超时等
                last = exc
                if attempt < RETRIES:
                    time.sleep(1.5 * (attempt + 1))
        raise last if last else RuntimeError("下载失败")

    def download(self, key: str, original_url: str) -> tuple[bytes, str, str]:
        """返回 (数据, 扩展名, 实际使用的地址)。"""
        with self._lock:
            cached = self._mem_cache.get(key)
        if cached:
            return cached[0], cached[1], key

        candidates = [key]
        norm_original = normalize_url(original_url)
        if not self.keep_query and norm_original != key:
            candidates.append(norm_original)  # 剥参数失败时退回原地址
        elif self.keep_query and norm_original not in candidates:
            candidates.append(norm_original)

        errors = []
        for url in candidates:
            try:
                data, ctype = self._fetch_with_retry(url)
            except Exception as exc:
                errors.append(f"{url} -> {exc}")
                continue
            ext = sniff_ext(data) or ext_from_content_type(ctype)
            if not ext:
                errors.append(f"{url} -> 返回的不是图片（Content-Type: {ctype or '未知'}）")
                continue
            with self._lock:
                if self._cache_bytes + len(data) <= 200 * 1024 * 1024:
                    self._mem_cache[key] = (data, ext)
                    self._cache_bytes += len(data)
            return data, ext, url

        raise RuntimeError("; ".join(errors) or "下载失败")


# ------------------------------------------------------------- 文章解析 ----


def split_front_matter(text: str) -> tuple[str, str]:
    """返回 (front matter 含分隔符, 正文)；没有 front matter 就返回 ('', text)。"""
    if not text.startswith("---"):
        return "", text
    lines = text.splitlines(keepends=True)
    if not lines or not FM_DELIM_RE.match(lines[0].rstrip("\r\n")):
        return "", text
    for idx in range(1, len(lines)):
        if FM_DELIM_RE.match(lines[idx].rstrip("\r\n")):
            return "".join(lines[: idx + 1]), "".join(lines[idx + 1:])
    return "", text


def iter_code_spans(line: str):
    """给出一行里行内代码 `...` 的区间，这些地方不替换。"""
    spans = []
    i, n = 0, len(line)
    while i < n:
        if line[i] == "`":
            j = i
            while j < n and line[j] == "`":
                j += 1
            ticks = line[i:j]
            end = line.find(ticks, j)
            if end == -1:
                break
            spans.append((i, end + len(ticks)))
            i = end + len(ticks)
        else:
            i += 1
    return spans


def apply_outside_code(line: str, func) -> str:
    """只对行内代码之外的片段执行 func。"""
    spans = iter_code_spans(line)
    if not spans:
        return func(line)
    out, pos = [], 0
    for start, end in spans:
        out.append(func(line[pos:start]))
        out.append(line[start:end])
        pos = end
    out.append(func(line[pos:]))
    return "".join(out)


def process_body(text: str, replacer) -> tuple[str, int]:
    """逐行处理正文，跳过 ``` 代码块。返回 (新文本, 替换次数)。"""
    lines = text.splitlines(keepends=True)
    out = []
    fence: str | None = None
    count = 0
    for line in lines:
        m = FENCE_RE.match(line)
        if m:
            marker = m.group("fence")[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            out.append(line)
            continue
        if fence is not None:
            out.append(line)
            continue
        new_line, n = apply_outside_code(line, replacer)
        count += n
        out.append(new_line)
    return "".join(out), count


def collect_refs(body: str, fm: str) -> list[ImageRef]:
    refs: list[ImageRef] = []
    seen: set[str] = set()
    fence = None
    for line in body.splitlines():
        m = FENCE_RE.match(line)
        if m:
            marker = m.group("fence")[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        for mm in MD_IMAGE_RE.finditer(line):
            url = mm.group("url")
            if is_remote(url):
                k = url_key(url)
                if k not in seen:
                    seen.add(k)
                    refs.append(ImageRef(url=url, key=k, kind="md"))
        for tag in HTML_IMG_RE.finditer(line):
            for sm in HTML_SRC_RE.finditer(tag.group(0)):
                url = sm.group("url")
                if is_remote(url):
                    k = url_key(url)
                    if k not in seen:
                        seen.add(k)
                        refs.append(ImageRef(url=url, key=k, kind="html"))
    # front matter 里的图片字段
    for raw in fm.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-"):
            value = stripped[1:].strip().strip("'\"")
            for u in BARE_URL_RE.findall(value):
                if is_remote(u):
                    k = url_key(u)
                    if k not in seen:
                        seen.add(k)
                        refs.append(ImageRef(url=u, key=k, kind="frontmatter"))
            continue
        if ":" in stripped:
            name, _, value = stripped.partition(":")
            if name.strip().lower() in FRONT_MATTER_IMAGE_FIELDS:
                for u in BARE_URL_RE.findall(value):
                    if is_remote(u):
                        k = url_key(u)
                        if k not in seen:
                            seen.add(k)
                            refs.append(ImageRef(url=u, key=k, kind="frontmatter"))
    return refs


def collect_local_missing(body: str, article_dir: str) -> list[str]:
    """检查本地相对引用的图片还在不在。"""
    missing = []
    for mm in MD_IMAGE_RE.finditer(body):
        url = mm.group("url").strip().strip("<>")
        if not url or is_remote(url) or url.startswith(("data:", "#", "mailto:")):
            continue
        if url.startswith("/"):
            continue  # 站内绝对路径，交给 Hugo 管
        rel = url.split("?", 1)[0].split("#", 1)[0]
        rel = urllib.parse.unquote(rel)
        if not IMG_EXT_RE.search(rel):
            continue
        if not os.path.exists(os.path.join(article_dir, rel)):
            missing.append(rel)
    return missing


# ------------------------------------------------------------- 清单管理 ----


class Manifest:
    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, dict] = {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                self.data = payload
        except (OSError, ValueError):
            self.data = {}

    def get_dir(self, article_dir: str) -> dict:
        return self.data.get(article_dir, {})

    def set_dir(self, article_dir: str, mapping: dict):
        self.data[article_dir] = mapping

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except OSError as exc:
            eprint(f"  ! 清单写入失败：{exc}")


# --------------------------------------------------------------- 主流程 ----


def find_articles(root: str, pattern: str) -> list[str]:
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in ("_tools", "node_modules", "public", "resources")
        ]
        if pattern in filenames:
            hits.append(os.path.join(dirpath, pattern))
    hits.sort()
    return hits


def write_original_copy(md_path: str, out_dir: str) -> bool:
    """在备份目录里另存一份改动前的原件（.index.md.bak），逐字节复制。"""
    bak = os.path.join(out_dir, BACKUP_SUFFIX)
    try:
        data = open(md_path, "rb").read()
        if os.path.exists(bak):
            with open(bak, "rb") as fh:
                if fh.read() == data:
                    return False        # 内容一致，不用重写
        os.makedirs(out_dir, exist_ok=True)
        tmp = bak + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, bak)
        return True
    except OSError as exc:
        eprint(f"    ! 原件副本写入失败：{exc}")
        return False


def mirror_article_dir(src_dir: str, out_dir: str, dry_run: bool = False) -> int:
    """把文章目录整棵复制到备份目录（保留子目录，跳过隐藏文件和工具产物）。"""
    if dry_run:
        count = 0
        for dirpath, dirnames, filenames in os.walk(src_dir):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            count += len([f for f in filenames if not f.startswith(".")])
        return count

    os.makedirs(out_dir, exist_ok=True)
    copied = 0
    for dirpath, dirnames, filenames in os.walk(src_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        rel = os.path.relpath(dirpath, src_dir)
        target_dir = out_dir if rel == "." else os.path.join(out_dir, rel)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as exc:
            eprint(f"    ! 建目录失败 {target_dir}：{exc}")
            continue
        for name in filenames:
            if name.startswith("."):    # .index.md.bak 等工具产物不带走
                continue
            src_file = os.path.join(dirpath, name)
            dst_file = os.path.join(target_dir, name)
            try:
                if (os.path.exists(dst_file)
                        and os.path.getsize(dst_file) == os.path.getsize(src_file)
                        and int(os.path.getmtime(dst_file)) == int(os.path.getmtime(src_file))):
                    continue            # 上次已经复制过且没变
                shutil.copy2(src_file, dst_file)
                copied += 1
            except OSError as exc:
                eprint(f"    ! 复制失败 {name}：{exc}")
    return copied


def plan_filenames(refs: list[ImageRef], article_dir: str, manifest_dir: dict, known: dict) -> dict:
    """先给每个 URL 分配文件名，避免同目录重名。"""
    taken = set()
    for entry in os.listdir(article_dir):
        if os.path.isfile(os.path.join(article_dir, entry)):
            taken.add(entry.lower())
    mapping = {}
    for ref in refs:
        if ref.key in known:
            mapping[ref.key] = known[ref.key]
            taken.add(known[ref.key].lower())
            continue
        prev = manifest_dir.get(ref.key)
        if prev:
            mapping[ref.key] = prev
            taken.add(prev.lower())
    return mapping, taken


def process_article(
    md_path: str,
    out_dir: str,
    downloader: Downloader,
    manifest: Manifest,
    args,
    index: int,
    total: int,
) -> ArticleStats:
    """读取 md_path，把图片和改写后的 md 写到 out_dir（原地模式时两者相同）。"""
    src_dir = os.path.dirname(md_path)
    rel_dir = os.path.relpath(src_dir, args.root)
    out_md_path = os.path.join(out_dir, os.path.basename(md_path))
    stats = ArticleStats(path=md_path)

    raw = open(md_path, "rb").read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig" if bom else "utf-8", errors="replace")

    fm, body = split_front_matter(text)
    refs = collect_refs(body, fm)
    stats.total_refs = len(refs)
    stats.remote_refs = len(refs)

    m_total = len(MD_IMAGE_RE.findall(body))
    stats.local_refs = max(0, m_total - len([r for r in refs if r.kind == "md"]))
    stats.missing_local = collect_local_missing(body, out_dir if os.path.isdir(out_dir) else src_dir)

    print(f"\n[{index}/{total}] {rel_dir}")
    if not refs:
        print("    · 没有网络图片，跳过")
        if stats.missing_local:
            print(f"    ! 有 {len(stats.missing_local)} 个本地图片找不到：")
            for p in stats.missing_local[:5]:
                print(f"      - {p}")
        return stats

    manifest_dir = manifest.get_dir(rel_dir)
    mapping, taken = plan_filenames(refs, out_dir, manifest_dir, {})

    # 1) 下载（并发）
    results: dict[str, DownloadResult] = {}
    pending = [r for r in refs if r.key not in mapping or not os.path.exists(
        os.path.join(out_dir, mapping.get(r.key, ""))
    )]
    already = [r for r in refs if r not in pending]

    for ref in already:
        fname = mapping[ref.key]
        results[ref.key] = DownloadResult(
            key=ref.key, ok=True, filename=fname,
            size=os.path.getsize(os.path.join(out_dir, fname)),
            source="本地已存在", from_cache=True,
        )

    if pending:
        done = 0
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {
                pool.submit(downloader.download, ref.key, ref.url): ref
                for ref in pending
            }
            for fut in as_completed(futures):
                ref = futures[fut]
                done += 1
                try:
                    data, ext, used = fut.result()
                except Exception as exc:
                    results[ref.key] = DownloadResult(key=ref.key, ok=False, error=str(exc))
                    stats.failed += 1
                    stats.failures.append((ref.url, str(exc)))
                    print(f"    [{done}/{len(pending)}] × 失败 {shorten(ref.url)}")
                    continue

                fname = make_filename(ref.key, ext)
                if fname.lower() in taken:
                    stem, e = os.path.splitext(fname)
                    fname = f"{stem}-{hashlib.md5(ref.key.encode()).hexdigest()[:6]}{e}"
                target = os.path.join(out_dir, fname)

                if not args.dry_run:
                    try:
                        with open(target, "wb") as fh:
                            fh.write(data)
                    except OSError as exc:
                        results[ref.key] = DownloadResult(key=ref.key, ok=False, error=f"写入失败：{exc}")
                        stats.failed += 1
                        stats.failures.append((ref.url, f"写入失败：{exc}"))
                        continue
                taken.add(fname.lower())
                mapping[ref.key] = fname
                results[ref.key] = DownloadResult(
                    key=ref.key, ok=True, filename=fname, size=len(data), source=used
                )
                stats.downloaded += 1
                print(f"    [{done}/{len(pending)}] ✓ {fname}  ({human_size(len(data))})")

    # 2) 改写链接
    ok_map = {k: v.filename for k, v in results.items() if v.ok and v.filename}
    stats.reused = len(already)

    def replace_md(match: re.Match) -> str:
        url = match.group("url")
        if not is_remote(url):
            return match.group(0)
        fname = ok_map.get(url_key(url))
        if not fname:
            return match.group(0)
        alt = match.group("alt")
        title = match.group("title") or ""
        return f"![{alt}]({fname}{title})"

    def repl_line(line: str) -> tuple[str, int]:
        count = 0

        def do_md(seg: str) -> str:
            nonlocal count
            def _sub(m):
                nonlocal count
                new = replace_md(m)
                if new != m.group(0):
                    count += 1
                return new
            return MD_IMAGE_RE.sub(_sub, seg)

        line = apply_outside_code(line, do_md)

        def do_html(match: re.Match) -> str:
            nonlocal count
            tag = match.group(0)

            def _sub_src(sm):
                nonlocal count
                url = sm.group("url")
                if is_remote(url):
                    fname = ok_map.get(url_key(url))
                    if fname:
                        count += 1
                        return f'{sm.group(1)}{sm.group(2)}{fname}{sm.group(2)}'
                return sm.group(0)

            return HTML_SRC_RE.sub(_sub_src, tag)

        line = HTML_IMG_RE.sub(do_html, line)
        return line, count

    new_body_lines = []
    total_replaced = 0
    fence = None
    for line in body.splitlines(keepends=True):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group("fence")[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            new_body_lines.append(line)
            continue
        if fence is not None:
            new_body_lines.append(line)
            continue
        nl = ""
        core = line
        if line.endswith("\r\n"):
            core, nl = line[:-2], "\r\n"
        elif line.endswith("\n"):
            core, nl = line[:-1], "\n"
        new_core, n = repl_line(core)
        total_replaced += n
        new_body_lines.append(new_core + nl)
    new_body = "".join(new_body_lines)

    # front matter：默认只下载不改（避免破坏 SEO 用的绝对地址）
    new_fm = fm
    if args.rewrite_front_matter and fm:
        def replace_fm_line(line: str) -> str:
            name, sep, value = line.partition(":")
            if sep and name.strip().lower() in FRONT_MATTER_IMAGE_FIELDS:
                for u in BARE_URL_RE.findall(value):
                    fname = ok_map.get(url_key(u))
                    if fname:
                        value = value.replace(u, fname)
                return f"{name}{sep}{value}"
            if line.strip().startswith("-"):
                for u in BARE_URL_RE.findall(line):
                    fname = ok_map.get(url_key(u))
                    if fname:
                        line = line.replace(u, fname)
            return line

        new_fm = "".join(
            replace_fm_line(ln) for ln in fm.splitlines(keepends=True)
        )

    stats.rewritten = total_replaced

    # 3) 落盘
    if not args.dry_run and (new_body != body or new_fm != fm):
        # 原地模式在这里留 .bak；导出模式的 .bak 由主循环统一写（覆盖没有网络图片的文章）
        if not args.no_backup and os.path.abspath(out_dir) == os.path.abspath(src_dir):
            bak = os.path.join(src_dir, BACKUP_SUFFIX)
            if not os.path.exists(bak):
                shutil.copy2(md_path, bak)
        data = (new_fm + new_body).encode("utf-8")
        if bom:
            data = b"\xef\xbb\xbf" + data
        tmp = out_md_path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, out_md_path)
        stats.changed = True

    manifest.set_dir(rel_dir, {k: v for k, v in mapping.items() if k in ok_map})

    summary = (
        f"    · 网络图片 {stats.remote_refs} 张：新下载 {stats.downloaded}，"
        f"已存在 {stats.reused}，失败 {stats.failed}；改写 {stats.rewritten} 处"
    )
    print(summary)
    if stats.missing_local:
        print(f"    ! 有 {len(stats.missing_local)} 个本地图片找不到：")
        for p in stats.missing_local[:5]:
            print(f"      - {p}")
    return stats


def shorten(url: str, limit: int = 78) -> str:
    return url if len(url) <= limit else url[: limit - 3] + "..."


# ------------------------------------------------------------------ 入口 ----


def interactive_menu(root: str | None = None) -> int:
    """双击 .bat 时看到的中文菜单。"""
    root = DEFAULT_ROOT if root is None else root
    dest = ""
    while True:
        if os.name == "nt":
            os.system("cls")
        print("=" * 66)
        print("  文章图片备份工具")
        print("=" * 66)
        print(f"\n  源目录：{root}")
        print(f"  备份到：{dest if dest else '（未设置）'}\n")
        print("  [1] 预览        —— 只看会做什么，不写任何文件")
        print("  [2] 导出备份    —— 复制到上面的备份文件夹，源目录完全不动")
        print("  [3] 原地备份    —— 图片直接存回文章目录（会改原文件）")
        print("  [4] 设置源目录  —— 要备份哪个文件夹")
        print("  [5] 设置备份目录")
        print("  [6] 打开报告文件夹")
        print("  [0] 退出\n")
        try:
            choice = input("  请输入数字后回车：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice == "0":
            return 0
        if choice in ("1", "2", "3"):
            if choice == "2" and not dest:
                dest = ask_folder("  备份到哪个文件夹？\n  （可以直接把文件夹拖进这个窗口）\n  路径：")
                if not dest:
                    continue
            if choice == "1":
                argv = [root, "--dry-run"] + (["--dest", dest] if dest else [])
            elif choice == "2":
                argv = [root, "--dest", dest]
            else:
                argv = [root]
            code = main(argv)
            print(f"\n（返回码 {code}：0=全部成功，3=有图片没下载成功）")
            input("  按回车回到菜单…")
        elif choice == "4":
            picked = ask_folder("  要备份哪个文件夹？\n  路径：")
            if picked:
                root = picked
        elif choice == "5":
            picked = ask_folder("  备份到哪个文件夹？\n  路径：")
            if picked:
                dest = picked
        elif choice == "6":
            os.makedirs(REPORT_DIR, exist_ok=True)
            try:
                if os.name == "nt":
                    os.startfile(REPORT_DIR)  # type: ignore[attr-defined]
                else:
                    print(f"  报告目录：{REPORT_DIR}")
                    input("  按回车继续…")
            except Exception as exc:
                print(f"  × 打不开：{exc}")
                input("  按回车继续…")


def ask_folder(prompt: str) -> str:
    """让用户输入一个文件夹路径，返回规范化后的绝对路径（失败返回空串）。"""
    try:
        raw = input(prompt).strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        return ""
    if not raw:
        return ""
    candidate = os.path.abspath(os.path.expanduser(raw))
    if os.path.isdir(candidate):
        return candidate
    # 目标目录可能还没建，允许创建
    parent = os.path.dirname(candidate)
    if os.path.isdir(parent) or os.path.isdir(os.path.dirname(parent)):
        return candidate
    print(f"  × 找不到这个路径：{candidate}")
    input("  按回车继续…")
    return ""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="把 Hugo 文章里的网络图片下载到本地，并把链接改成相对引用。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例子：\n"
            "  python backup_images.py --dry-run          看看会做什么，不改文件\n"
            "  python backup_images.py                    正式执行\n"
            "  python backup_images.py D:\\blog\\content   处理指定目录\n"
        ),
    )
    p.add_argument("root", nargs="?", default=DEFAULT_ROOT, help="要扫描的根目录（默认：本工具上一级目录）")
    p.add_argument("--dest", "-d", metavar="目录",
                   help="导出模式：把所有结果另存到这个文件夹，源文件夹完全不动")
    p.add_argument("--pattern", default="index.md", help="文章文件名（默认 index.md）")
    p.add_argument("--dry-run", action="store_true", help="只预览，不下载、不修改、不写清单")
    p.add_argument("--workers", type=int, default=6, help="并发下载数（默认 6）")
    p.add_argument("--keep-query", action="store_true", help="保留 URL 里的图片处理参数（默认剥掉以取原图）")
    p.add_argument("--no-backup", action="store_true", help="不生成 .index.md.bak 备份")
    p.add_argument("--rewrite-front-matter", action="store_true",
                   help="同时把 front matter 里的图片地址改成相对文件名（默认只下载不改）")
    p.add_argument("--limit", type=int, default=0, help="只处理前 N 篇文章（测试用）")
    p.add_argument("--quiet", action="store_true", help="少打印点")
    p.add_argument("--menu", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return p


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    argv = list(sys.argv[1:] if argv is None else argv)
    if "--menu" in argv:
        rest = [a for a in argv if a != "--menu"]
        if rest:            # 把文件夹拖到 .bat 上：作为源目录打开菜单
            candidate = os.path.abspath(rest[0].strip('"'))
            if os.path.isdir(candidate):
                return interactive_menu(candidate)
            eprint(f"× 这个路径不是文件夹：{candidate}")
            return 2
        return interactive_menu()

    args = build_parser().parse_args(argv)
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        eprint(f"× 目录不存在：{root}")
        return 2
    args.root = root

    # ---- 导出模式：结果写到别的文件夹，源目录只读 ----
    dest = None
    if args.dest:
        dest = os.path.abspath(os.path.expanduser(args.dest.strip().strip('"')))
        if dest == root:
            eprint("× 备份目录不能和源目录是同一个地方。")
            return 2
        if dest.startswith(root.rstrip(os.sep) + os.sep):
            eprint("× 备份目录不能放在源目录里面（会把自己备份进去）。")
            eprint(f"   源目录：{root}")
            eprint(f"   备份到：{dest}")
            eprint("   建议换到源目录的「旁边」或「外面」，例如：")
            eprint(f"   源目录：{root}")
            eprint(f"   备份到：{os.path.join(os.path.dirname(root), os.path.basename(root) + '-备份')}")
            return 2
        if root.startswith(dest.rstrip(os.sep) + os.sep):
            eprint("× 源目录位于备份目录内部，这样会互相覆盖。")
            return 2
        if not args.dry_run:
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError as exc:
                eprint(f"× 无法创建备份目录 {dest}：{exc}")
                return 2
    args.dest = dest

    started = time.time()
    print("=" * 72)
    print(f" Hugo 文章图片备份工具 v{VERSION}")
    print("=" * 72)
    print(f"源目录  ：{root}")
    if dest:
        print(f"备份到  ：{dest}")
        print(f"模式    ：{'预览（不会写入任何文件）' if args.dry_run else '导出备份（源目录只读，不动它）'}")
    else:
        print(f"模式    ：{'预览（不修改任何文件）' if args.dry_run else '原地备份（图片存回文章目录）'}")

    articles = find_articles(root, args.pattern)
    if args.limit:
        articles = articles[: args.limit]
    if not articles:
        print(f"\n× 在 {root} 下没找到任何 {args.pattern}")
        return 1
    print(f"文章数量：{len(articles)}")

    downloader = Downloader(keep_query=args.keep_query, workers=args.workers)
    manifest = Manifest(
        os.path.join(dest, ".image-backup-manifest.json") if dest else MANIFEST_PATH
    )

    all_stats: list[ArticleStats] = []
    mirrored = 0
    baks = 0
    for i, md in enumerate(articles, 1):
        src_dir = os.path.dirname(md)
        rel_dir = os.path.relpath(src_dir, root)
        out_dir = os.path.join(dest, rel_dir) if dest else src_dir
        if args.dry_run:
            print(f"\n[{i}/{len(articles)}] {rel_dir}")
            if dest:
                print(f"    → 将导出到 {out_dir}")
            raw = open(md, "rb").read().decode("utf-8-sig", errors="replace")
            fm, body = split_front_matter(raw)
            refs = collect_refs(body, fm)
            all_stats.append(ArticleStats(
                path=md, total_refs=len(refs), remote_refs=len(refs),
                missing_local=collect_local_missing(
                    body, out_dir if os.path.isdir(out_dir) else src_dir
                ),
            ))
            if refs:
                print(f"    · 发现 {len(refs)} 张网络图片")
                for ref in refs[:3]:
                    print(f"      - {shorten(ref.url, 90)}")
                if len(refs) > 3:
                    print(f"      … 另外 {len(refs) - 3} 张")
            continue
        try:
            if dest:
                mirrored += mirror_article_dir(src_dir, out_dir, False)
                if not args.no_backup and write_original_copy(md, out_dir):
                    baks += 1
            all_stats.append(
                process_article(md, out_dir, downloader, manifest, args, i, len(articles))
            )
        except Exception as exc:  # 单篇出错不影响整体
            eprint(f"  ! 处理失败 {md}：{exc}")

    if not args.dry_run:
        manifest.save()

    # ---------------- 汇总 ----------------
    total_refs = sum(s.remote_refs for s in all_stats)
    total_down = sum(s.downloaded for s in all_stats)
    total_reuse = sum(s.reused for s in all_stats)
    total_fail = sum(s.failed for s in all_stats)
    total_rewrite = sum(s.rewritten for s in all_stats)
    changed = sum(1 for s in all_stats if s.changed)
    failures = [(s.path, u, e) for s in all_stats for (u, e) in s.failures]
    missing = [(s.path, p) for s in all_stats for p in s.missing_local]

    elapsed = time.time() - started
    print("\n" + "=" * 72)
    print(" 汇总" + ("（预览模式，未做任何修改）" if args.dry_run else ""))
    print("=" * 72)
    print(f"  文章      ：{len(articles)} 篇（{changed} 篇被修改）")
    if dest:
        print(f"  备份位置  ：{dest}")
        if not args.dry_run:
            print(f"  复制文件  ：{mirrored} 个")
            print(f"  原件副本  ：{baks} 篇（每篇多一份 {BACKUP_SUFFIX}）")
    print(f"  网络图片  ：{total_refs} 张引用")
    if not args.dry_run:
        print(f"  新下载    ：{total_down} 张")
        print(f"  已存在    ：{total_reuse} 张")
        print(f"  失败      ：{total_fail} 张")
        print(f"  链接改写  ：{total_rewrite} 处")
    if missing:
        print(f"  本地缺图  ：{len(missing)} 个引用找不到文件")
    print(f"  耗时      ：{elapsed:.1f} 秒")

    # 写报告
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"backup-{stamp}.txt")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(f"# Hugo 图片备份报告 {datetime.now():%Y-%m-%d %H:%M:%S}\n")
        fh.write(f"# 源目录：{root}\n")
        if dest:
            fh.write(f"# 备份到：{dest}\n")
            if not args.dry_run:
                fh.write(f"# 复制文件：{mirrored} 个；原件副本 {baks} 篇（{BACKUP_SUFFIX}）\n")
        fh.write(f"# 模式：{'预览' if args.dry_run else ('导出备份' if dest else '原地备份')}\n\n")
        fh.write(f"文章 {len(articles)} 篇，网络图片引用 {total_refs} 张，"
                 f"新下载 {total_down}，已存在 {total_reuse}，失败 {total_fail}，改写 {total_rewrite} 处\n\n")
        for s in all_stats:
            if s.remote_refs or s.missing_local:
                fh.write(f"{os.path.relpath(s.path, root)}\n")
                fh.write(f"  网络图片 {s.remote_refs} 张，下载 {s.downloaded}，失败 {s.failed}，改写 {s.rewritten} 处\n")
                for p in s.missing_local:
                    fh.write(f"  缺图：{p}\n")
        if failures:
            fh.write("\n## 下载失败清单（下次运行会自动重试）\n")
            for path, url, err in failures:
                fh.write(f"{os.path.relpath(path, root)}\n  {url}\n  {err}\n")
    print(f"  报告      ：{report_path}")

    if failures:
        print("\n以下图片没下载成功，链接保持原样（下次运行会自动重试）：")
        for path, url, err in failures[:10]:
            print(f"  - {os.path.relpath(path, root)}")
            print(f"    {shorten(url, 100)}")
            print(f"    原因：{shorten(err, 120)}")
        if len(failures) > 10:
            print(f"  … 共 {len(failures)} 条，详见报告文件")

    print("\n完成。")
    return 0 if total_fail == 0 else 3


if __name__ == "__main__":
    sys.exit(main())
