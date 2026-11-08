# 王志满律师 · 民事诉讼与行政诉讼实务笔记

> 本仓库是个人博客的源代码。线上站点：**[2019527.xyz](https://2019527.xyz)**

本站用来存放办案手记、类案复盘、诉讼程序笔记与文书模板，内容以民事诉讼、行政诉讼及司法案例研究为主，另有一小部分建站笔记与生活随笔。截至2026年11月8日，目前有 57 篇文章、约 12.7 万字。

站内文章涉及的人物、金额、案号均已作脱敏处理，只讨论一般性的法律问题，**不构成针对任何个案的法律意见**。内容性质与转载规则见站内《免责声明》，个人信息处理说明见《隐私政策》。

## 站点一览

| 项目 | 内容 |
| --- | --- |
| 网址 | https://2019527.xyz |
| 文章 | 57 篇 · 约 12.7 万字 |
| 栏目 | 工作（41）· 学习（9）· 生活（7），下设非诉实务、诉讼实务、案例复盘、文书模板、办案工具、法律科普、建站笔记、日常随笔等子类 |
| 搜索 | Pagefind 本地静态索引，不依赖第三方服务 |
| 评论 | Twikoo |
| 订阅 | [/index.xml](https://2019527.xyz/index.xml)（RSS） |
| 文章许可 | CC BY-NC-SA 4.0（注明作者与出处） |

## 技术栈

| 环节 | 用的东西 |
| --- | --- |
| 生成 | Hugo 0.169.0 extended |
| 主题 | FixIt（Git 子模块，锁定在指定版本） |
| 发布 | GitHub Pages + GitHub Actions，推送到 `main` 即自动构建上线 |
| 搜索 | Pagefind 1.4.0，构建时生成中文索引 |
| 评论 | Twikoo 云函数 |
| 统计 | 百度统计 + vercount 阅读量 |
| 配置 | `config/_default`（通用）、`config/production`（正式站点地址） |

两个小特色：每篇文章除网页外还会生成一份 `/index.md` 纯净 Markdown，方便 AI 助手和检索工具直接读取正文；`layouts/robots.txt` 放行 AI 爬虫，并声明内容可用于回答引用、不用于模型训练。

## 发一篇新文章（全程在网页上点，不用装软件）

1. 打开 `https://github.com/wangzhiman123/blog/tree/main/content/posts`。
2. 点右上角 **Add file** → **Create new file**。
3. 在文件名框里填 `文件夹名/index.md`，例如 `appeal-fee-waiver/index.md`（GitHub 会自动建好文件夹）。**这个文件夹名就是文章网址**，建议用短英文或拼音，中文标题会变成一长串编码，不利于分享。
4. 把下面这段粘进去，改成自己的内容：

```yaml
---
title: "文章标题"
date: 2026-11-08T09:00:00+08:00
categories:
- 工作
- 诉讼实务
tags:
- 立案
- 诉讼费
summary: "一句话摘要，显示在首页文章列表"
description: "一句话摘要，显示在搜索结果和分享卡片"
authors:
- 王志满律师
---

正文从这里开始写……
```

5. 拉到页面底部点绿色 **Commit changes**（弹窗里再确认一次）。
6. 等 2–5 分钟刷新网站就能看到；没出现就去仓库的 **Actions** 页，看构建是不是绿色勾。

几个容易踩的坑：

- 开头两个 `---` 之间这段叫 **front matter**（可以理解为「文章的身份证」），缩进和短横线别改坏。
- `authors` 必须写 `王志满律师`，一字不差，否则作者归档页会分裂成两个。
- `categories` 第一层只能是 **工作 / 学习 / 生活**，第二层从现有子类里选；实在没有合适的再新增。
- 标签从下面「标签约定」里挑 2–4 个，标签是给读者按主题找文章的，不是文章的内容摘要。
- `date` 用 `2026-11-08T09:00:00+08:00` 这种完整格式，末尾 `+08:00` 表示北京时间。

## 提交后自动完成的事（不用手动做）

- 构建 Hugo、压缩资源并发布到 GitHub Pages。
- 生成 Pagefind 搜索索引、站点地图 `sitemap.xml`、RSS。
- 为每篇文章生成 `/index.md` 纯净 Markdown 版本。
- 把新文章地址推送给百度与 IndexNow（需在仓库 Secrets 里配置 `BAIDU_TOKEN`）。
- 每天凌晨 4:10 自动重建一次，让首页「热门文章」榜跟着阅读量更新。

## 常用文件速查

| 想改什么 | 打开哪个文件 |
| --- | --- |
| 站点名称 | `config/production/hugo.toml` 里的 `title` |
| 正式网址 | `config/production/hugo.toml` 的 `baseURL` + `static/CNAME` |
| 站点描述、关键词、作者 | `config/production/params.toml` |
| 首页副标题、菜单排序 | `config/_default/params.toml`、`config/_default/menus.toml` |
| 关于 / 隐私政策 / 免责声明 | `content/about/`、`content/privacy/`、`content/disclaimer/` 下的 `index.md` |
| 友情链接 | `data/friends.yml` |
| 搜索引擎验证标签 | `layouts/_partials/custom/seo-verify.html` |
| 爬虫规则 | `layouts/robots.txt` |
| 页脚法务链接 | `layouts/_partials/custom/footer-legal.html` |
| 构建与部署流程 | `.github/workflows/deploy.yml`（内有版本锁定和升级说明） |
| 辅助脚本 | `tools/fetch-pv.py`（阅读量）、`tools/submit-urls.py`（推送收录）、`tools/make-og-image.ps1`（分享图） |

## 标签约定

写新文章时优先从下面这些标签里挑，别随手造新词；确有必要新增时，先看看是不是已有标签换了个说法。

- **程序与阶段**：立案、一审阶段、二审阶段、执行阶段、再审、管辖、驳回起诉、送达、财产保全、追加被告、原告方、被告方、仲裁
- **业务与主题**：律师调查、公司工商档案、户籍信息、银行账户查询、商品房定金、民间借贷、婚姻家事、知识产权、合同纠纷、租赁合同、电子证据、公证认证、社保医保、起诉状、律师费、诉讼费、律师职业、法律分析
- **内容形式**：实务教程、资料下载、普法问答、案例复盘
- **地域**：江西南昌
- **生活与建站**：生活随笔、家庭生活、健康生活、生活办事、建站笔记、域名与网址、文章排版、GitHub、WorkBuddy、AI 工具

英文产品名用官方写法（GitHub、WorkBuddy），地名统一写「江西南昌」。只服务一篇文章的一次性标签尽量不要新增——每个标签都会生成一个独立页面，标签太碎会稀释整站的收录效果。

## 维护提醒

- **版本已锁死**：`deploy.yml` 里 Hugo、Pagefind、Dart Sass 的版本都是固定值。升级前先看 Hugo 的 Breaking changes，一次只改一处，改完盯一眼线上。
- **换域名要改三处**：`config/production/hugo.toml` 的 `baseURL`（结尾必须有斜杠）、`static/CNAME`、以及关于／隐私／免责三页里提到的域名。
- **主题自动更新**：`.github/workflows/update-theme.yml` 是每周自动更新主题的工作流。主题是 beta 版，自动更新曾覆盖过自定义配置，建议在 Actions 页把它停用，需要时再手动升级。
- **老文章的网址不要批量改**：GitHub Pages 做不了 301 跳转，改名会丢掉已收录的链接和外链；新文章用语义化网址即可。
- **本地预览（进阶，可跳过）**：电脑上装好 Hugo extended 后，在仓库目录执行 `hugo server`，浏览器打开 `http://localhost:1313` 就能边写边看。

## 许可

- 仓库内的模板与脚本代码沿用上游的 MIT 许可，见 `LICENSE`。
- 站内文章内容采用 **CC BY-NC-SA 4.0**，转载请注明作者与出处，具体以站内《免责声明》为准。
