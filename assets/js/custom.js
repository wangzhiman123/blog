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

  /** 轻提示：复制成功之类的一句话反馈 */
  function toast(msg) {
    var el = document.getElementById('custom-toast')
    if (!el) {
      el = document.createElement('div')
      el.id = 'custom-toast'
      el.className = 'custom-toast'
      document.body.appendChild(el)
    }
    el.textContent = msg
    el.classList.add('is-show')
    clearTimeout(toast.timer)
    toast.timer = setTimeout(function () {
      el.classList.remove('is-show')
    }, 2200)
  }

  /** 复制文本，老内核也尽量能用 */
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text)
    }
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea')
      ta.value = text
      ta.setAttribute('readonly', '')
      ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0'
      document.body.appendChild(ta)
      ta.select()
      ta.setSelectionRange(0, text.length)
      var ok = false
      try {
        ok = document.execCommand('copy')
      } catch (e) {
        ok = false
      }
      document.body.removeChild(ta)
      ok ? resolve() : reject(new Error('copy failed'))
    })
  }

  /**
   * 分享按钮
   * 桌面端点微信 → 弹二维码（Hugo 构建时生成的 PNG）
   * 手机端点微信 → 弹二维码没法扫，直接复制链接让用户粘到微信里
   */
  function initShare() {
    var mask = document.getElementById('post-share-qr')
    var hasCopy = document.querySelector('[data-share-copy]')
    if (!mask && !hasCopy) return

    function openQr() {
      if (!mask) return
      mask.classList.add('is-open')
      mask.setAttribute('aria-hidden', 'false')
    }
    function closeQr() {
      if (!mask) return
      mask.classList.remove('is-open')
      mask.setAttribute('aria-hidden', 'true')
    }
    function isMobile() {
      return /Android|iPhone|iPad|iPod|Mobile|MicroMessenger/i.test(navigator.userAgent)
    }
    function doCopy() {
      copyText(location.href)
        .then(function () {
          toast('链接已复制')
        })
        .catch(function () {
          toast('复制失败，请手动复制地址栏')
        })
    }

    document.addEventListener('click', function (e) {
      var el = e.target
      if (!el || !el.closest) return

      if (el.closest('[data-share-wechat]')) {
        e.preventDefault()
        if (isMobile()) {
          copyText(location.href)
            .then(function () {
              toast('链接已复制，去微信里粘贴给好友')
            })
            .catch(function () {
              toast('复制失败，请手动复制地址栏')
            })
        } else {
          openQr()
        }
        return
      }

      if (el.closest('[data-share-close]') || el === mask) {
        closeQr()
        return
      }

      if (el.closest('[data-share-copy]')) {
        e.preventDefault()
        doCopy()
      }
    })

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeQr()
    })
  }

  function init() {
    mirrorBusuanzi()
    initToBottom()
    initPageJump()
    initShare()
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', init)
  else
    init()
})()
