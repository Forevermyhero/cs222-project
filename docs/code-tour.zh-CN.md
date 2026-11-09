# 代码导读：每个文件究竟负责什么

## 先理解当前版本

现在已经能跑通：**填写旅行需求 → 查询示例/公开地图数据 → 排出候选行程 → 检查约束 → 网页展示行程和来源**。

当前规划器是 Python 规则算法，**没有连接 LLM，也不会调用 OpenAI 或产生模型 API 费用**。
公开地图接口不需要 API key，但仍需要网络允许访问对应域名。示例模式完全离线。
系统只给出计划和待确认事项，不查询余票、不支付、不替用户完成预订。

`src` 是 source code 的常见缩写。实际应用代码都在这里，测试、文档和运行脚本单独放置。

```text
src/
├── __init__.py
├── backend/
│   ├── __init__.py
│   └── app/
│       ├── __init__.py
│       ├── main.py
│       ├── models.py
│       ├── validator.py
│       ├── time_utils.py
│       ├── streaming.py
│       └── services/
│           ├── __init__.py
│           ├── pipeline.py
│           ├── providers.py
│           ├── opening_hours.py
│           ├── generation.py
│           ├── research.py
│           └── demo.py
└── frontend/
    ├── index.html
    └── static/
        ├── app.js
        ├── api.js
        ├── render.js
        └── style.css
```

## 一次点击经过哪些文件

1. 浏览器打开 [index.html](../src/frontend/index.html)，显示表单和结果区域。
2. [app.js](../src/frontend/static/app.js) 读取目的地、日期、偏好、固定事件等字段。
3. [api.js](../src/frontend/static/api.js) 把这些字段作为 JSON 发给 Flask。
4. [main.py](../src/backend/app/main.py) 接收请求，使用数据模型检查字段是否合法。
5. [streaming.py](../src/backend/app/streaming.py) 把真实执行步骤逐条发送回浏览器。
6. [pipeline.py](../src/backend/app/services/pipeline.py) 组织地点查询、营业时间、排程和验证。
7. [render.js](../src/frontend/static/render.js) 显示日程、查询记录、问题和准备事项。

前端不直接调用地图供应商。网络查询集中在后端，便于控制超时、缓存、请求频率和证据记录。

## 后端：入口与规则

| 文件 | 实际做什么 |
| --- | --- |
| [main.py](../src/backend/app/main.py) | Flask 应用入口。`create_app()` 建立网页和 API 路由；接收 JSON、调用服务、返回结果，并把输入错误和服务失败转换成 HTTP 响应。它不负责排程算法。 |
| [models.py](../src/backend/app/models.py) | 定义 `Location`、`Activity`、`Trip`、`PlanRequest`、`ValidationRequest` 等 Pydantic 模型。检查空字段、时区、金额、重复 ID、坐标和数据规模。这里的 models 是数据契约，不是数据库表。 |
| [validator.py](../src/backend/app/validator.py) | `validate_itinerary()` 独立检查原始固定事件、重叠、交通间隔、营业窗口、旅行日期和可选预算。只读取输入，不访问网络、不修改行程。返回具体问题和缺数据警告。 |
| [time_utils.py](../src/backend/app/time_utils.py) | `localize()` 把表单的本地时间解释为指定时区的时间，识别夏令时导致的重复或不存在时刻。其他计算转换成 UTC 比较。 |
| [streaming.py](../src/backend/app/streaming.py) | 将规划过程放入有数量限制的工作线程，通过队列把进度送给 HTTP 响应。前端无需等待全部查询完成才看到信息。处理取消、错误、心跳和总超时；它不判断行程是否合理。 |

### 为什么单独保留固定事件

候选行程中的 `fixed=true` 标签不足以证明没有移动固定安排。
例如用户原本输入 10:00–11:00 面试，候选行程改成了 11:00–12:00，仍然必须被发现。
因此 `ValidationRequest` 同时包含：

- `trip.activities`：准备展示的候选行程。
- `original_fixed_events`：用户原始固定安排，作为独立比较基准。

验证器按 ID 比较事件是否存在、起止时间是否改变、地点/名称/固定标签是否改变。

## 后端：services 中的分工

| 文件 | 实际做什么 |
| --- | --- |
| [pipeline.py](../src/backend/app/services/pipeline.py) | 总协调器。`plan_trip()` 创建本次请求的查询日志；保留原始固定事件；收集地点和交通数据；生成营业窗口；调用排程器；最后调用验证器。返回完整结果、来源和准备事项。 |
| [providers.py](../src/backend/app/services/providers.py) | 唯一的公开数据 HTTP 适配层。`city()` 调 Open-Meteo；`find_place()` 调 Nominatim；`attractions()` 调 Overpass；`travel_matrix()` 调 OSRM。负责超时、缓存、频率控制和请求/缓存/失败记录。不会让 LLM 猜测事实。 |
| [opening_hours.py](../src/backend/app/services/opening_hours.py) | 把支持的 OSM 营业时间表达式转换成具体日期的时间窗口，例如 `Mo-Fr 09:00-17:00`。支持有限语法；节假日、日出日落等无法解释时返回未知，不擅自补营业时间。它不自行访问网络。 |
| [generation.py](../src/backend/app/services/generation.py) | 当前候选排程器。`heuristic_plan()` 在 09:00–18:00 内按 15 分钟步长寻找可安排的 60 分钟访问；`fits()` 检查插入后与相邻活动的重叠和交通间隔。安排不下的地点会被列出。这里目前没有 LLM 调用。 |
| [research.py](../src/backend/app/services/research.py) | 定义 `ResearchLog`，整理实际查询步骤、地图记录链接和来源字段，并生成“出发前确认”建议。过滤危险链接。日志是公开工具活动，不是模型的隐藏思考过程。 |
| [demo.py](../src/backend/app/services/demo.py) | 提供 Chicago 的示例地点、合成费用/营业时间和表单示例输入。它提供的是测试事实，具体活动时间仍由排程器根据输入计算。示例不会访问网站。 |

### 四个免费数据服务分别提供什么

| 服务 | 提供的信息 | 注意事项 |
| --- | --- | --- |
| Open-Meteo geocoding | 城市坐标、城市时区 | 不是天气功能；目前只用它定位城市。 |
| Nominatim | 用户明确指定的地点或固定事件地址 | 不做自动补全/批量地理编码；每秒最多一次请求。 |
| Overpass / OpenStreetMap | 附近景点、已有的营业时间和网站标签 | 社区数据可能缺失或过期。网站标签不代表已访问该网站。 |
| OSRM | 地点之间的有方向的驾车时间估计 | 不包含实时交通，不代表步行或公共交通。 |

这些服务无需密钥。当前云环境需要将四个域名加入允许列表后才能完成真实调用；
网络拒绝会被显示为失败，不会换成示例后声称是真实数据。

## 前端：页面、交互、请求、显示分开

| 文件 | 实际做什么 |
| --- | --- |
| [index.html](../src/frontend/index.html) | 页面结构，包括旅行表单、固定事件输入、日程区域、Research log 和 Before you go。这里不写排程算法。 |
| [app.js](../src/frontend/static/app.js) | 页面控制器。读取输入、增删固定事件、加载示例、开始/停止请求、重新验证和下载结果。它决定什么时候调用网络模块和渲染模块。 |
| [api.js](../src/frontend/static/api.js) | 网络模块。`requestJSON()` 请求普通 JSON；`streamPlan()` 按行读取规划进度流，并识别成功结果和错误。它只调用我们自己的 Flask 服务。 |
| [render.js](../src/frontend/static/render.js) | 显示模块。把返回数据变成行程卡片、来源卡片、验证问题和准备清单。使用 `textContent` 显示外部/用户文字，避免把它们当 HTML 执行；外链只允许普通 HTTP(S) 链接。 |
| [style.css](../src/frontend/static/style.css) | 视觉样式与桌面/手机适配。控制配色、布局、卡片、字体和查询状态动画。没有外部字体、图片服务或构建框架依赖。 |

### Research log 中的状态怎么解释

- `running`：实际操作正在执行。
- `completed`：该操作已完成；收到 API JSON 不等于访问了场馆官网。
- `cached`：使用了缓存，没有在本次重新请求该地址。
- `failed`：请求或规划步骤失败。
- `example`：离线示例事实，明确没有访问真实网站。

来源卡片的 `website_checked=false` 表示官网链接没有被抓取验证。
准备事项的 `booking_required=null`、`availability_checked=false` 表示预订政策和库存仍未知。
所以界面建议“检查门票政策”，而不是断言“已确认需要买票”或“还有余票”。

`index.html` 由 Flask 加载，才能得到正确的静态资源路径；实际交互需要先运行后端。

## 测试：这些文件不会参与正常业务处理

| 文件 | 检查内容 |
| --- | --- |
| [tests/conftest.py](../tests/conftest.py) | 提供独立、可重复的输入对象和 Flask 测试客户端；禁止测试意外访问真实网络。 |
| [tests/test_models.py](../tests/test_models.py) | 检查错误类型、金额、时区、日期、重复 ID、坐标等输入问题。 |
| [tests/test_validator.py](../tests/test_validator.py) | 检查各项约束、边界、夏令时、精确金额、所有重叠对和不修改输入。 |
| [tests/test_services.py](../tests/test_services.py) | 用假响应测试数据接口、缓存/限流、营业时间转换和候选排程。假响应测试不证明真实服务可访问。 |
| [tests/test_api.py](../tests/test_api.py) | 检查 Flask 页面、静态文件、状态码、错误响应以及 API 与验证器的一致性。 |
| [tests/test_research.py](../tests/test_research.py) | 检查查询证据、缓存标记、安全链接、预订未知状态，以及查询没结束时前端就能收到进度。 |

## 脚本、示例、配置和文档

| 文件 | 用途 |
| --- | --- |
| [scripts/smoke_browser.py](../scripts/smoke_browser.py) | 驱动真实 Chromium 检查桌面/手机流程，保存截图和下载结果；默认不请求公开数据服务。需要单独安装浏览器测试工具。 |
| [scripts/smoke_live.py](../scripts/smoke_live.py) | 主动请求真实免费地图服务，检查地理编码、景点、地点解析和路线；失败时退出码非零。 |
| [examples/plan-demo.json](../examples/plan-demo.json) | 一份完整的表单规划 API 示例输入。 |
| [examples/validate-valid.json](../examples/validate-valid.json) | 一份带候选行程、原始固定事件和事实的直接验证示例。 |
| [requirements.in](../requirements.in) | 人维护的直接依赖范围，包括 Flask、Pydantic、requests 和测试工具。 |
| [requirements.lock](../requirements.lock) | 确定的安装版本及哈希，用于复现安装；不写业务逻辑。 |
| [pyproject.toml](../pyproject.toml) | pytest 测试目录和 coverage 统计范围。 |
| [.flake8](../.flake8) | Python 风格检查设置。 |
| [.gitignore](../.gitignore) | 避免提交缓存、虚拟环境、临时测试输出和 `.env`。 |
| [.github/workflows/tests.yml](../.github/workflows/tests.yml) | GitHub 推送/PR 后自动运行安装、风格和离线测试。 |
| [README.md](../README.md) | 安装、启动、模式和检查命令的入口。 |
| [docs/architecture.md](architecture.md) | 组件与调用关系。 |
| [docs/mvp-spec.md](mvp-spec.md) | API 字段、验证规则、时间边界和进度流协议。 |
| [docs/implementation-plan.md](implementation-plan.md) | 已完成内容与下一步任务。 |
| [docs/test-plan.md](test-plan.md) | 测试范围和真实/模拟验证边界。 |
| [docs/validation-report.md](validation-report.md) | 实际执行结果、尚未验证项和网络阻碍。 |
| [docs/checkin4-demo.md](checkin4-demo.md) | 面谈的演示顺序、简短英文介绍和可以请教的问题。 |
| [docs/screenshots/](screenshots/) | 浏览器生成的桌面、手机和查询日志截图，仅用于展示。 |

各目录中的 `__init__.py` 只负责标记 Python 包，方便导入，不包含隐藏的业务功能。
`src/__init__.py`、`src/backend/__init__.py`、`src/backend/app/__init__.py`、
`src/backend/app/services/__init__.py`、`tests/__init__.py` 和 `scripts/__init__.py` 都属于这种文件。

## 推荐阅读顺序

先看 `main.py` 的路由，再看 `PlanRequest` 和 `pipeline.plan_trip()`，接着看
`generation.heuristic_plan()` 与 `validator.validate_itinerary()`。最后回到前端，按
`app.js → api.js → render.js` 阅读。这样能把一次点击和真正执行的函数对应起来。

## LLM 后续接在哪里

未来可用一个模型适配器生成同样的候选活动，或者让模型选择调用现有的地点/路线工具。
目前的工具由 Python 按固定顺序调用；没有声称模型已经自主浏览网页。

无论模型是否能联网，营业时间和交通信息都需要来源。缺少结构化数据时，可以再研究
读取官方网页或搜索工具，并记录引用。模型给出的文字本身不应直接成为“已验证事实”。
模型服务的免费额度、API key、地区和计费限制需要单独确认；这轮原型没有接入模型服务。
