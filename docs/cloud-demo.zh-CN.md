# 云端在线交互：完整后端与网页

目标是打开一个 HTTPS 地址，输入城市，让云端 Python 调用公开地图工具，并把实际结果返回网页。
托管对象包括 Flask API、工具台和原有行程页面。此方案使用 Render 的免费 Web Service，
不需要模型 API key，也不创建数据库。

## 部署步骤

1. 打开[从本仓库部署到 Render](https://render.com/deploy?repo=https://github.com/Forevermyhero/cs222-project)。
2. 用自己的 GitHub 账号登录，按页面要求授权访问这个项目仓库。
3. 检查 Blueprint 识别了根目录 `render.yaml`，服务为 `itinerary-that-holds-up`、计划为 **Free**。
4. 创建服务，等待安装与启动结束。复制 Render 实际分配的 HTTPS 网址。
5. 在该网址末尾添加 `/tools`，打开数据工具台。根路径 `/` 仍是行程页面。

当前没有可用的 Render 登录连接，账号登录和创建服务需要仓库拥有者在 Render 完成。
配置文件提交和本地部署检查不等于服务已经发布。实际网址只有部署完成后才能确认。
Render 免费实例闲置会休眠，首次访问可能需要等待唤醒。本配置关闭自动部署；以后更新 main 后，
可在 Render 选择手动部署最新提交。

## 如何现场演示在线请求

1. 打开 `/api/health`，确认 HTTP 200、`status=ok`。这只能证明应用在线，不能证明地图服务可达。
2. 打开 `/tools`，目的地输入 `Chicago`，保持“真实公开数据”，点击开始。
3. 查看城市坐标、时区、附近景点、营业时间原文、网站标签和驾车时间。
4. 展开某次调用的结构化数据，核对来源 URL。换一个城市再次查询，观察数据变化。
5. 选择不同的 A/B 地点，再查两个方向的驾车时间，下载查询 JSON。
6. 可选：填写一个明确景点名称，通过后端 Nominatim 工具解析它。

浏览器开发者工具 Network 中应出现同一站点的 `/api/tools/city`、`/api/tools/attractions`、
`/api/tools/routes` 等 POST。页面收到的是云端 API 的响应；公开供应商的查询 URL 保存在来源记录中。
缓存命中会明确标注，不能把缓存结果称为本次新的网络查询。

地图数据可能缺失或服务可能拒绝请求。失败应保留来源和错误，不能改用合成数据并声称查询成功。
离线示例可单独演示输入、显示和排程，但不能作为成功获取实时地图数据的证据。
营业时间未与官网交叉确认；票价、酒店库存、步行/公交和预订仍未实现。

## 配置与文件职责

- `render.yaml`：声明免费 Python Web Service、构建命令、启动命令和健康检查。
- `src/backend/gunicorn_config.py`：读取 Render 提供的 `PORT`，绑定所有接口，使用 Gunicorn gthread。
  仅一个进程共享缓存和 Nominatim 限流，四个线程允许进度流和普通请求并行。
- `requirements.in` / `requirements.lock`：加入 Linux 云服务所需的 Gunicorn，保留确定版本与哈希。

在 Linux 上本地验证同一启动入口：

```sh
PORT=8001 python -m gunicorn --config python:src.backend.gunicorn_config \
  --bind 127.0.0.1:8001 'src.backend.app.main:create_app()'
```

Gunicorn 服务的 210 秒超时覆盖应用 180 秒规划期限。Render 负责公网 HTTPS；Gunicorn 监听内部端口。
应用健康检查与外部数据查询需要分别验证。当前 Codex 实例的出站白名单并不描述 Render 的网络状态。

## 验证状态

最新 Plan 页面更新改用酒店入住示例，增加活动来源、排程方法和步骤解释，并改进其他城市输入。
这部分在本地验证通过；仓库配置关闭自动部署，需要手动部署最新提交才会更新公网版本。
详见[Plan 页面导读](planner-walkthrough.zh-CN.md)。下文 `cf4c5b4` 为之前版本的历史上线证据。

2026-11-09，用户提供的 Render 部署日志确认提交 `cf4c5b4` 构建成功，Gunicorn 在内部端口
10000 启动，`/api/health` 持续返回 200，并显示 `Your service is live`。

- [在线工具台](https://itinerary-that-holds-up.onrender.com/tools)
- [在线行程页面](https://itinerary-that-holds-up.onrender.com/)

用户提供的在线页面结果还确认：Chicago 离线示例生成 5 个活动，原始面试保持在 10:00–11:00，
验证为零违规、零警告，显示 7 条真实的本地处理/示例步骤。这证明云端示例交互已经运行。
这些步骤并不代表访问了 7 个网站；20 分钟交通、费用和营业时间仍是合成示例。

Codex 直接请求公开域名时，当前代理返回 `CONNECT tunnel failed, response 403`；
该域名已加入环境配置草稿，但保存草稿不代表策略已应用。因此这里没有声称独立完成远端 HTTP
检查或成功查询实时地图数据。下一步在在线 `/tools` 使用真实公开数据并核对结果/来源。
本地执行证据见 `docs/validation-report.md`。
