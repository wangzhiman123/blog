/**
 * 站点自定义脚本
 *
 * 1. 把不蒜子更新的隐藏数值镜像到页眉/页脚带文字标签的节点
 * 2. 悬浮"回到底部"按钮的显隐与滚动
 *
 * 说明：主题在 busuanzi.site_views=false 时仍会渲染带 id 的隐藏节点，
 * 不蒜子脚本按 id 写入数字，这里只做搬运与千分位格式化，不重复统计。
 */
(function () {
  'use strict'

  /** 千分位格式化 */
  function formatNumber(raw) {
    var n = Number(raw)
    return Number.isFinite(n) ? n.toLocaleString('zh-CN') : String(raw)
  }

  /** 读取某个节点里的纯数字，读不到返回空串 */
  function readNumber(el) {
    if (!el)
      return ''
    var text = (el.textContent || '').trim()
    return /^\d+$/.test(text) ? text : ''
  }

  /**
   * 不蒜子的数值是异步写入的，用轮询兜底：
   * 一旦全部读到就停止，最长等 30 秒。
   */
  function mirrorBusuanzi() {
    var mapping = [
      ['busuanzi_value_site_pv', ['header-site-pv', 'header-site-pv-mobile']],
      ['busuanzi_value_site_uv', []],
    ]

    function tick() {
      var missing = 0
      mapping.forEach(function (pair) {
        var value = readNumber(document.getElementById(pair[0]))
        pair[1].forEach(function (id) {
          var el = document.getElementById(id)
          if (!el)
            return
          if (value) {
            if (el.textContent !== formatNumber(value))
              el.textContent = formatNumber(value)
          }
          else {
            missing++
          }
        })
      })
      return missing === 0
    }

    if (tick())
      return

    var tries = 0
    var timer = window.setInterval(function () {
      tries++
      if (tick() || tries > 60)
        window.clearInterval(timer)
    }, 500)
  }

  /** 回到底部按钮 */
  function initToBottom() {
    var button = document.querySelector('.to-bottom')
    if (!button)
      return

    var doc = document.documentElement

    function update() {
      var scrollable = doc.scrollHeight - window.innerHeight > 200
      var atBottom = window.innerHeight + window.scrollY >= doc.scrollHeight - 120
      button.classList.toggle('hidden', !scrollable || atBottom)
    }

    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    update()

    button.addEventListener('click', function () {
      window.scrollTo({ top: doc.scrollHeight, behavior: 'smooth' })
    })
  }

  /**
   * 分页器「跳至第 N 页」
   *
   * 主题只渲染页码，本站 9 页，想翻到中间某页得一下下点。
   * 这里读最后一个页码链接反推总页数与 URL 前缀（/page/2/ 这种），
   * 再插一个输入框，回车或点按钮直接跳。
   */
  function initPageJump() {
    var list = document.querySelector('.pagination')
    if (!list || list.dataset.jumpReady === '1')
      return

    var anchors = list.querySelectorAll('a[href]')
    if (!anchors.length)
      return

    // 模板对最后一页不做折叠，所以最后一个链接必然是末页
    var lastHref = anchors[anchors.length - 1].getAttribute('href') || ''
    var matched = lastHref.match(/^(.*\/page\/)(\d+)\/?$/)
    if (!matched)
      return

    var prefix = matched[1]
    var total = parseInt(matched[2], 10)
    if (!(total > 1))
      return

    var home = prefix.replace(/page\/$/, '')
    var active = list.querySelector('.page-item.active a')
    var current = active ? parseInt(active.textContent, 10) || 1 : 1

    list.dataset.jumpReady = '1'

    var box = document.createElement('div')
    box.className = 'page-jump'
    box.innerHTML = '跳至第 <input type="number" min="1" max="' + total
      + '" inputmode="numeric" aria-label="输入页码，共 ' + total + ' 页" placeholder="' + current
      + '"> 页 <button type="button">跳转</button>'

    var input = box.querySelector('input')
    var button = box.querySelector('button')

    function go() {
      var n = parseInt(input.value, 10)
      if (!Number.isFinite(n) || n < 1 || n > total) {
        input.style.borderColor = '#f85149'
        input.focus()
        return
      }
      window.location.href = n === 1 ? home : prefix + n + '/'
    }

    button.addEventListener('click', go)
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter')
        go()
    })
    input.addEventListener('input', function () {
      input.style.borderColor = ''
    })

    list.insertAdjacentElement('afterend', box)
  }

  // ---------------------------------------------------------------------------
  // 友链页：头像加载失败时换成默认头像
  // 头像引用的是对方站点的图片，随时可能失效或触发防盗链，不能让它显示成破图。
  // 不用事件委托（旧内核的 SVG 元素没有 closest），逐个绑定。
  // ---------------------------------------------------------------------------
  function initFriendAvatarFallback() {
    var imgs = document.querySelectorAll('.friend-links img.friend-avatar')
    if (!imgs.length)
      return

    var fallback = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
      + '<rect width="100" height="100" rx="8" fill="#d8d8d8"/>'
      + '<circle cx="50" cy="50" r="32" stroke="#8c8c8c" stroke-width="3" fill="none" opacity="0.55"/>'
      + '<circle cx="38" cy="42" r="3.5" fill="#8c8c8c" opacity="0.7"/>'
      + '<circle cx="62" cy="42" r="3.5" fill="#8c8c8c" opacity="0.7"/>'
      + '<path d="M36 58c4 6 24 6 28 0" stroke="#8c8c8c" stroke-width="3" fill="none" opacity="0.6" stroke-linecap="round"/>'
      + '</svg>'
    )

    function replace(img) {
      if (img.getAttribute('data-avatar-failed') === '1')
        return
      img.setAttribute('data-avatar-failed', '1')
      img.classList.add('is-fallback')
      img.removeAttribute('srcset')
      img.src = fallback
    }

    for (var i = 0; i < imgs.length; i++) {
      (function (img) {
        img.addEventListener('error', function () { replace(img) })
        // 绑定监听之前就已经失败的，补一次判断
        if (img.complete && img.naturalWidth === 0)
          replace(img)
      })(imgs[i])
    }
  }

  // ---------------------------------------------------------------------------
  // 友链页：搜索框
  // 按 data-search（站点名称 + 简介，已小写）做包含匹配，空格分隔视为「同时满足」
  // ---------------------------------------------------------------------------
  function initFriendSearch() {
    var input = document.getElementById('friend-search-input')
    if (!input)
      return

    var clearBtn = document.getElementById('friend-search-clear')
    var emptyTip = document.getElementById('friend-empty')
    var totalNum = document.getElementById('friend-total-num')
    var groups = document.querySelectorAll('.friend-group')
    var cards = document.querySelectorAll('.friend-links .friend-link')
    if (!cards.length)
      return

    var total = cards.length
    if (totalNum)
      totalNum.setAttribute('data-all', String(total))

    function textOf(card) {
      var t = card.getAttribute('data-search')
      if (!t) {
        t = (card.textContent || '').toLowerCase()
        card.setAttribute('data-search', t)
      }
      return t
    }

    function apply() {
      var q = input.value.replace(/^\s+|\s+$/g, '').toLowerCase()
      var words = q ? q.split(/\s+/) : []
      var shown = 0

      for (var i = 0; i < cards.length; i++) {
        var card = cards[i]
        var text = textOf(card)
        var hit = true
        for (var j = 0; j < words.length; j++) {
          if (text.indexOf(words[j]) === -1) {
            hit = false
            break
          }
        }
        if (hit) {
          card.removeAttribute('hidden')
          shown++
        }
        else {
          card.setAttribute('hidden', '')
        }
      }

      // 整组都没命中就收起这个分区，避免留下一排空标题
      for (var k = 0; k < groups.length; k++) {
        var members = groups[k].querySelectorAll('.friend-link')
        var any = false
        for (var m = 0; m < members.length; m++) {
          if (!members[m].hasAttribute('hidden')) {
            any = true
            break
          }
        }
        if (any)
          groups[k].removeAttribute('hidden')
        else
          groups[k].setAttribute('hidden', '')
      }

      if (clearBtn)
        clearBtn.hidden = !q
      if (emptyTip)
        emptyTip.hidden = shown !== 0
      if (totalNum)
        totalNum.textContent = q ? String(shown) : totalNum.getAttribute('data-all')
    }

    input.addEventListener('input', apply)
    input.addEventListener('search', apply)
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && input.value) {
        input.value = ''
        apply()
      }
    })

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        input.value = ''
        apply()
        input.focus()
      })
    }

    apply()
  }

  // ---------------------------------------------------------------------------
  // 列表卡片的阅读量与评论数
  //
  // Hugo 构建期拿不到这两个数字，模板只输出短横线占位，这里异步补齐：
  //   阅读量 ← VerCount  GET  https://events.vercount.one/api/v2/log?url=<完整URL>
  //   评论数 ← Twikoo    POST <env_id> {event:"GET_COMMENTS_COUNT", urls:[路径...]}
  //
  // 两家都是本站已经在用的服务（页脚访问量、文章页评论区），不需要额外部署。
  // 结果缓存 5 分钟，翻页来回走不重复请求；接口挂了就把那一项藏起来，
  // 不留一排短横线在卡片上。
  // ---------------------------------------------------------------------------
  var POST_STATS_KEY = 'post-stats:v1'
  var POST_STATS_TTL = 5 * 60 * 1000

  function readPostStatsCache() {
    var empty = { ts: Date.now(), views: {}, comments: {} }
    try {
      var raw = window.localStorage.getItem(POST_STATS_KEY)
      if (!raw)
        return empty
      var saved = JSON.parse(raw)
      if (!saved || typeof saved.ts !== 'number' || !saved.views || !saved.comments)
        return empty
      // 过期就整份丢掉，重新查一遍
      if (Date.now() - saved.ts > POST_STATS_TTL)
        return empty
      return saved
    }
    catch (e) {
      // 无痕模式或禁用了本地存储时 localStorage 会抛错
      return empty
    }
  }

  function savePostStatsCache(cache) {
    try {
      cache.ts = Date.now()
      window.localStorage.setItem(POST_STATS_KEY, JSON.stringify(cache))
    }
    catch (e) { /* 存不了就算了，不影响显示 */ }
  }

  /** 带超时的 fetch，任何失败都返回 null，绝不抛错 */
  function fetchJson(url, options, timeout) {
    if (typeof window.fetch !== 'function' || typeof window.AbortController !== 'function')
      return Promise.resolve(null)

    var controller = new window.AbortController()
    var timer = window.setTimeout(function () { controller.abort() }, timeout || 6000)
    var opts = options || {}
    opts.signal = controller.signal
    opts.mode = 'cors'
    opts.credentials = 'omit'

    return window.fetch(url, opts).then(function (res) {
      return res.ok ? res.json() : null
    }).catch(function () {
      return null
    }).then(function (data) {
      window.clearTimeout(timer)
      return data
    })
  }

  /** 并发上限为 limit 的任务池；任务自身不 reject，所以不需要错误分支 */
  function runLimitedPool(tasks, limit) {
    return new Promise(function (resolve) {
      if (!tasks.length) {
        resolve()
        return
      }
      var index = 0
      var running = 0
      var done = 0

      function pump() {
        while (running < limit && index < tasks.length) {
          running++
          tasks[index]().then(function () {
            running--
            done++
            if (done === tasks.length)
              resolve()
            else
              pump()
          })
          index++
        }
      }
      pump()
    })
  }

  /** 写入一个数字；value 为 null 表示没取到，隐藏整项 */
  function applyStat(node, value) {
    if (typeof value === 'number' && isFinite(value)) {
      var num = node.querySelector('.post-stat-num')
      if (num)
        num.textContent = formatNumber(value)
      node.classList.remove('is-hidden')
    }
    else {
      node.classList.add('is-hidden')
    }
  }

  function initPostStats() {
    var viewNodes = document.querySelectorAll('.post-views[data-views-url]')
    var commentNodes = document.querySelectorAll('.post-comments[data-comments-path]')
    if (!viewNodes.length && !commentNodes.length)
      return

    var cache = readPostStatsCache()
    var changed = false

    // ---- 评论数：一次 POST 批量取全部路径 ----
    var env = ''
    var boxes = document.querySelectorAll('.post-stats[data-twikoo-env]')
    for (var b = 0; b < boxes.length; b++) {
      var candidate = boxes[b].getAttribute('data-twikoo-env')
      if (candidate) {
        env = candidate.replace(/\/+$/, '')
        break
      }
    }

    if (env && commentNodes.length) {
      var wanted = []
      var queued = {}
      var pending = []

      for (var c = 0; c < commentNodes.length; c++) {
        var cNode = commentNodes[c]
        var path = cNode.getAttribute('data-comments-path')
        if (!path)
          continue
        if (typeof cache.comments[path] === 'number') {
          applyStat(cNode, cache.comments[path])
        }
        else {
          pending.push({ node: cNode, path: path })
          if (!queued[path]) {
            queued[path] = true
            wanted.push(path)
          }
        }
      }

      if (wanted.length) {
        fetchJson(env + '/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ event: 'GET_COMMENTS_COUNT', urls: wanted })
        }, 8000).then(function (data) {
          // 注意：Twikoo 成功时只返回 {data:[...], accessToken}，没有 code 字段；
          // 出错时才给 {message:"..."}。所以这里只认 data 是不是数组。
          var got = {}
          if (data && Array.isArray(data.data)) {
            for (var i = 0; i < data.data.length; i++) {
              var row = data.data[i]
              if (row && typeof row.url === 'string' && typeof row.count === 'number')
                got[row.url] = row.count
            }
          }

          var hit = false
          for (var j = 0; j < pending.length; j++) {
            var p = pending[j]
            if (typeof got[p.path] === 'number') {
              cache.comments[p.path] = got[p.path]
              applyStat(p.node, got[p.path])
              hit = true
            }
            else {
              applyStat(p.node, null)
            }
          }
          if (hit)
            savePostStatsCache(cache)
        })
      }
    }
    else if (commentNodes.length) {
      // 没启用 Twikoo 就别显示评论数，留个短横线没意义
      for (var k = 0; k < commentNodes.length; k++)
        applyStat(commentNodes[k], null)
    }

    // ---- 阅读量：一个地址一次请求，并发 3 条 ----
    if (!viewNodes.length)
      return

    var todo = []
    var seen = {}
    for (var v = 0; v < viewNodes.length; v++) {
      var vNode = viewNodes[v]
      var url = vNode.getAttribute('data-views-url')
      if (!url)
        continue
      if (typeof cache.views[url] === 'number')
        applyStat(vNode, cache.views[url])
      else if (!seen[url]) {
        seen[url] = true
        todo.push(url)
      }
    }

    if (!todo.length)
      return

    var tasks = todo.map(function (url) {
      return function () {
        return fetchJson(
          'https://events.vercount.one/api/v2/log?url=' + encodeURIComponent(url),
          null,
          6000
        ).then(function (data) {
          var pv = data && data.data && typeof data.data.page_pv === 'number'
            ? data.data.page_pv
            : null

          if (pv !== null) {
            cache.views[url] = pv
            changed = true
          }

          for (var n = 0; n < viewNodes.length; n++) {
            if (viewNodes[n].getAttribute('data-views-url') === url)
              applyStat(viewNodes[n], pv)
          }
        })
      }
    })

    runLimitedPool(tasks, 3).then(function () {
      if (changed)
        savePostStatsCache(cache)
    })
  }

  // ---------------------------------------------------------------------------
  // 文章页的阅读量
  //
  // 主题在标题下方留了 <span id="twikoo_visitors">-</span>，这个位置本来是给
  // Twikoo 的 visitor 功能填的，但 FixIt 的 js/lib/twikoo.ts 只调用了 init() 和
  // getCommentsCount()，从没调用过取阅读量的那个方法，所以它永远是短横线。
  //
  // 这里用与首页卡片同一套 VerCount 数据补齐，两处显示的数字才一致。
  // （Twikoo 自己也有一个计数器，但它从没被调用过，历史数据是 0，换过去等于从零开始。）
  // ---------------------------------------------------------------------------
  function initArticleViews() {
    var node = document.getElementById('twikoo_visitors')
    if (!node)
      return

    // 优先用 canonical，它是构建期写死的完整地址，带不带 www、有没有尾斜杠都以它为准
    var link = document.querySelector('link[rel="canonical"]')
    var url = (link && link.getAttribute('href')) || window.location.href
    var holder = node.closest ? node.closest('.comment-visitors') : null

    function hide() {
      // 取不到就整项藏掉，留个「– 次阅读」反而像坏了
      if (holder)
        holder.classList.add('is-hidden')
    }

    var cache = readPostStatsCache()
    if (typeof cache.views[url] === 'number') {
      node.textContent = formatNumber(cache.views[url])
      return
    }

    fetchJson(
      'https://events.vercount.one/api/v2/log?url=' + encodeURIComponent(url),
      null,
      6000
    ).then(function (data) {
      var pv = data && data.data && typeof data.data.page_pv === 'number'
        ? data.data.page_pv
        : null

      if (pv === null) {
        hide()
        return
      }

      cache.views[url] = pv
      savePostStatsCache(cache)
      node.textContent = formatNumber(pv)
    })
  }

  // ---------------------------------------------------------------------------
  // 修复脚注「正文 → 文末」跳转失效
  //
  // FixIt 主题在 params.toml 开启 tooltip = true 时，会给脚注引用链接
  // （a.footnote-ref）绑定 click 事件并 e.preventDefault() 拦截默认跳转，
  // 目的是让悬停气泡正常工作，却连点击跳转也一起禁掉了。
  // （文末 → 正文的 a.footnote-backref 不在拦截范围，所以那一向是好的。）
  //
  // 这里在「捕获阶段」手动完成跳转：捕获阶段先于冒泡阶段执行，
  // 等主题那个 preventDefault 的监听器（冒泡阶段）轮到的时候，
  // 我们已经在捕获阶段把 location.hash 设好了，跳转照常发生。
  // 悬停气泡不受影响，点击跳转也恢复了，两边兼得。
  // ---------------------------------------------------------------------------
  function initFootnoteJump() {
    document.addEventListener('click', function (e) {
      var link = e.target && e.target.closest
        ? e.target.closest('a.footnote-ref')
        : null
      if (!link)
        return
      var href = link.getAttribute('href')
      // 只处理锚点跳转（如 #fn:1），忽略真正的外部链接
      if (!href || href.charAt(0) !== '#')
        return
      var target = document.getElementById(href.slice(1))
      if (!target)
        return
      e.preventDefault()
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
      // 同步更新地址栏的 hash，保持浏览器「前进/后退」行为一致
      if (window.history && window.history.replaceState)
        window.history.replaceState(null, '', href)
    }, true)
  }

  // ---------------------------------------------------------------------------
  // 正文配图：点一下放大查看，再点一下（或按 Esc）还原
  //
  // 站点的 lightgallery 是关掉的，Markdown 图片也没有被 <a> 包起来，
  // 所以这里用 document 上的事件委托自己做一个极简灯箱：不依赖第三方库、
  // 不改任何文章 Markdown、全站文章一次性生效。
  // 放大时把图床链接里的 w_800 换成 w_1600，让大图仍然是清楚的；
  // 万一取不到大图，自动退回页面里已经加载好的那张。
  // 灯箱内支持滚轮 / +− 按钮缩放（1–8 倍，以鼠标位置为锚点），放大后可按住
  // 拖动、用方向键或触屏单指滑动查看长图，不再被「适应窗口」的高度限制住。
  // 放大状态不会误触关闭，关闭统一交给 × / Esc / 复位后点一下。
  // ---------------------------------------------------------------------------

  /** 由页面里的小图地址推算出放大用的大图地址 */
  function getLargeImageUrl(src) {
    if (!src)
      return src
    // 协议相对地址（//q*.itc.cn/...）补上当前页面的协议
    var url = src.charAt(0) === '/' && src.charAt(1) === '/'
      ? window.location.protocol + src
      : src
    // 只对本站在用的阿里云 OSS 系图床（搜狐 q*.itc.cn）改写参数，
    // 其它图源一律用原地址，避免加上不支持的参数导致 404
    if (!/^https?:\/\/q\d+\.itc\.cn\//i.test(url))
      return url
    if (/[?&]x-oss-process=/i.test(url))
      return url.replace(/([?&]x-oss-process=image\/resize,)w_\d+/i, '$1w_1600')
    return url + (url.indexOf('?') === -1 ? '?' : '&')
      + 'x-oss-process=image/resize,w_1600/format,webp'
  }

  // 说明：正文配图一律按单张显示（420px 宽、左对齐、文字在下方换行），
  //   不做自动分列，也不做浮动绕排。

  function initImageZoom() {
    var overlay = null
    var previousOverflow = ''

    function onKeyDown(e) {
      if (e.key === 'Escape' || e.keyCode === 27)
        close()
    }

    function close() {
      if (!overlay)
        return
      var node = overlay
      overlay = null
      node.classList.remove('is-open')
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
      // 等淡出动画走完再移除节点
      window.setTimeout(function () {
        if (node.parentNode)
          node.parentNode.removeChild(node)
      }, 200)
    }

    function open(img) {
      close() // 保险：先收掉可能残留的旧灯箱
      previousOverflow = document.body.style.overflow

      overlay = document.createElement('div')
      overlay.className = 'wb-lightbox'
      overlay.setAttribute('role', 'dialog')
      overlay.setAttribute('aria-label', '图片放大查看')
      overlay.setAttribute('tabindex', '-1')

      // 结构：遮罩 > 可滚动视口 > 舞台 > 画布 > 图片。
      // 舞台 width:max-content + min-width:100%：小图居中，放大溢出时左侧
      // 不会被 flex 居中裁掉，滚动条能一路看完整张长图。
      var viewport = document.createElement('div')
      viewport.className = 'wb-lightbox__viewport'
      viewport.setAttribute('tabindex', '-1')
      var stage = document.createElement('div')
      stage.className = 'wb-lightbox__stage'
      var canvas = document.createElement('div')
      canvas.className = 'wb-lightbox__canvas'

      var big = document.createElement('img')
      big.className = 'wb-lightbox__img'
      big.alt = img.alt || ''
      big.draggable = false
      big.src = getLargeImageUrl(img.getAttribute('src') || img.currentSrc || img.src)
      // 大图加载失败就退回页面上已经显示的那张，不会出现空白
      big.addEventListener('error', function () {
        var fallback = img.currentSrc || img.src
        if (big.src !== fallback)
          big.src = fallback
      })

      canvas.appendChild(big)
      stage.appendChild(canvas)
      viewport.appendChild(stage)

      var closeBtn = document.createElement('button')
      closeBtn.className = 'wb-lightbox__close'
      closeBtn.type = 'button'
      closeBtn.setAttribute('aria-label', '关闭')
      closeBtn.textContent = '×'

      var toolbar = document.createElement('div')
      toolbar.className = 'wb-lightbox__toolbar'
      var level = document.createElement('span')
      level.className = 'wb-lightbox__level'
      level.textContent = '100%'

      function toolButton(text, label, handler) {
        var b = document.createElement('button')
        b.type = 'button'
        b.className = 'wb-lightbox__btn'
        b.textContent = text
        b.setAttribute('aria-label', label)
        b.addEventListener('click', function (e) {
          e.stopPropagation()
          handler()
        })
        return b
      }

      var hint = document.createElement('div')
      hint.className = 'wb-lightbox__hint'

      // ---- 缩放状态 ----
      var MIN_SCALE = 1
      var MAX_SCALE = 8
      var scale = 1
      var baseW = 0
      var baseH = 0
      var dragging = false
      var moved = false
      var startX = 0, startY = 0, startLeft = 0, startTop = 0

      function clamp(v, lo, hi) {
        return v < lo ? lo : (v > hi ? hi : v)
      }

      function setHint() {
        hint.textContent = scale > 1
          ? '按住拖动或用方向键查看长图 · 点 × / Esc 关闭'
          : '滚轮或 +/− 缩放 · 点一下还原 · Esc 关闭'
      }

      /** 图片加载完成后算出「适应窗口」的基准尺寸，进入可缩放状态 */
      function fitImage() {
        var nw = big.naturalWidth
        var nh = big.naturalHeight
        if (!nw || !nh || big.classList.contains('is-ready'))
          return
        var maxW = Math.max(200, viewport.clientWidth - 48)
        var maxH = Math.max(200, viewport.clientHeight - 96)
        var fit = Math.min(maxW / nw, maxH / nh, 1)
        baseW = Math.round(nw * fit)
        baseH = Math.round(nh * fit)
        big.style.width = baseW + 'px'
        big.style.height = baseH + 'px'
        big.classList.add('is-ready')
        applyZoom(MIN_SCALE)
      }

      /** 以 (ax, ay) 这个屏幕点为锚点缩放，锚点下的画面保持不动 */
      function applyZoom(next, ax, ay) {
        if (!baseW || !baseH)
          return
        next = clamp(next, MIN_SCALE, MAX_SCALE)
        var rect = viewport.getBoundingClientRect()
        var vw = viewport.clientWidth
        var vh = viewport.clientHeight
        if (ax == null) ax = rect.left + vw / 2
        if (ay == null) ay = rect.top + vh / 2

        var oldW = baseW * scale
        var oldH = baseH * scale
        var oldLeft = (Math.max(vw, oldW) - oldW) / 2
        var oldTop = (Math.max(vh, oldH) - oldH) / 2
        var cx = viewport.scrollLeft + (ax - rect.left)
        var cy = viewport.scrollTop + (ay - rect.top)
        var ux = clamp(oldW ? (cx - oldLeft) / oldW : 0.5, 0, 1)
        var uy = clamp(oldH ? (cy - oldTop) / oldH : 0.5, 0, 1)

        scale = next
        var newW = baseW * scale
        var newH = baseH * scale
        canvas.style.width = Math.round(newW) + 'px'
        canvas.style.height = Math.round(newH) + 'px'
        big.style.transform = 'scale(' + scale + ')'
        level.textContent = Math.round(scale * 100) + '%'
        if (scale > 1)
          overlay.classList.add('is-zoomed')
        else
          overlay.classList.remove('is-zoomed')
        setHint()

        var newLeft = (Math.max(vw, newW) - newW) / 2
        var newTop = (Math.max(vh, newH) - newH) / 2
        viewport.scrollLeft = Math.max(0, newLeft + ux * newW - (ax - rect.left))
        viewport.scrollTop = Math.max(0, newTop + uy * newH - (ay - rect.top))
      }

      big.addEventListener('load', fitImage)

      var zoomOut = toolButton('−', '缩小', function () { applyZoom(scale / 1.25) })
      var zoomIn = toolButton('+', '放大', function () { applyZoom(scale * 1.25) })
      var reset = toolButton('复位', '恢复适应窗口', function () { applyZoom(MIN_SCALE) })
      toolbar.appendChild(zoomOut)
      toolbar.appendChild(level)
      toolbar.appendChild(zoomIn)
      toolbar.appendChild(reset)

      overlay.appendChild(viewport)
      overlay.appendChild(closeBtn)
      overlay.appendChild(toolbar)
      overlay.appendChild(hint)
      document.body.appendChild(overlay)
      document.body.style.overflow = 'hidden'
      document.addEventListener('keydown', onKeyDown)
      setHint()

      // 缓存命中时 load 不会再触发，这里补一次（此时已插入 DOM，能取到尺寸）
      if (big.complete && big.naturalWidth)
        fitImage()

      // 强制一次重排，让淡入动画生效
      void overlay.offsetWidth
      overlay.classList.add('is-open')
      viewport.focus()

      // 滚轮缩放（passive:false 才能阻止页面跟着滚）
      viewport.addEventListener('wheel', function (e) {
        if (!baseW)
          return
        e.preventDefault()
        applyZoom(scale * (e.deltaY < 0 ? 1.2 : 1 / 1.2), e.clientX, e.clientY)
      }, { passive: false })

      // 键盘：+ / - / 0；方向键、PageUp/Down 交给滚动容器原生处理
      viewport.addEventListener('keydown', function (e) {
        if (e.key === '+' || e.key === '=') {
          e.preventDefault()
          applyZoom(scale * 1.25)
        } else if (e.key === '-' || e.key === '_') {
          e.preventDefault()
          applyZoom(scale / 1.25)
        } else if (e.key === '0') {
          e.preventDefault()
          applyZoom(MIN_SCALE)
        }
      })

      // 鼠标按住拖动查看（触屏交给 overflow:auto 的原生单指滑动）
      viewport.addEventListener('pointerdown', function (e) {
        if (e.pointerType === 'touch' || e.button !== 0)
          return
        dragging = true
        moved = false
        startX = e.clientX
        startY = e.clientY
        startLeft = viewport.scrollLeft
        startTop = viewport.scrollTop
        if (scale > 1)
          viewport.classList.add('is-dragging')
        try { viewport.setPointerCapture(e.pointerId) } catch (err) {}
      })
      viewport.addEventListener('pointermove', function (e) {
        if (!dragging)
          return
        var dx = e.clientX - startX
        var dy = e.clientY - startY
        if (Math.abs(dx) > 4 || Math.abs(dy) > 4)
          moved = true
        if (scale > 1) {
          viewport.scrollLeft = startLeft - dx
          viewport.scrollTop = startTop - dy
          e.preventDefault()
        }
      })
      function endDrag() {
        dragging = false
        viewport.classList.remove('is-dragging')
      }
      viewport.addEventListener('pointerup', endDrag)
      viewport.addEventListener('pointercancel', endDrag)

      // 未放大时点一下还原；放大状态下不误关，只用 × / Esc 关闭
      overlay.addEventListener('click', function (e) {
        var t = e.target
        if (!t || !t.closest)
          return
        if (t.closest('.wb-lightbox__close')) {
          close()
          return
        }
        if (t.closest('.wb-lightbox__toolbar'))
          return
        if (moved) {
          moved = false
          return
        }
        if (scale > 1)
          return
        close()
      })
    }

    document.addEventListener('click', function (e) {
      var target = e.target
      if (!target || !target.closest)
        return
      if (target.closest('.wb-lightbox'))
        return // 灯箱内部交给上面的 close，不要重复处理
      var img = target.closest('.page.single .content img:not([width]):not([height])')
      if (!img)
        return
      // 带修饰键 / 非左键的点击不拦截（留给浏览器自己的行为）
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0)
        return
      open(img)
    })
  }

  function init() {
    mirrorBusuanzi()
    initToBottom()
    initPageJump()
    initPostStats()
    initArticleViews()
    initFriendAvatarFallback()
    initFriendSearch()
    initFootnoteJump()
    initImageZoom()
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', init)
  else
    init()
})()
