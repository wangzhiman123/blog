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

  function init() {
    mirrorBusuanzi()
    initToBottom()
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', init)
  else
    init()
})()
