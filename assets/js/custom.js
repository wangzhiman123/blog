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

  function init() {
    mirrorBusuanzi()
    initToBottom()
    initPageJump()
    initFriendAvatarFallback()
    initFriendSearch()
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', init)
  else
    init()
})()
