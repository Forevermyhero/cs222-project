# 数据工具台：先查看事实，再考虑规划

## 已实现

后端启动后打开 `/tools`。也可下载仓库中的 `docs/travel-tools.zip`，解压后双击
`travel-tools.html`。下载版是打包的真实交互页面，不是录像或查询日志回放。

1. 输入城市，例如 Chicago，选择“真实公开数据”后开始查询。
2. 查看城市经纬度、时区，以及查询地址和结构化返回数据。
3. 查看城市中心 3 公里内的少量博物馆、景点、画廊。当前不是热度排行榜。
4. 查看每个地点的坐标、OSM 标识、营业时间原文和网站标签。
5. 自动查询前两个地点的驾车时间；之后可选择 A/B 再查。两个方向分别展示。
6. 展开每次调用的返回数据，或下载本次证据 JSON。

查询执行期间先出现“正在查询”，完成后显示返回数据；失败会保留错误和已取得的数据。
交通服务失败不会生成假的驾车时间。空营业时间显示“未知”，不解释为全天开放。
城市定位当前取第一个匹配，附近景点并不代表整个城市的所有活动。

离线示例只支持 Chicago，坐标、营业时间、20 分钟交通都是合成示例。切换模式必须点击
“开始查询数据”才能重新采集；已显示的结果仍属于上一次采集，JSON 保存实际数据模式。

## 两种运行方式

| 方式 | 网络查询由谁执行 | 可用工具 |
| --- | --- | --- |
| 后端 `/tools` | Python `PublicDataClient` | 城市、明确地点/地址、附近景点、驾车时间 |
| 下载独立版 | 用户自己的浏览器，依赖服务 CORS 支持 | 城市、附近景点、驾车时间 |

独立版不需要 API key、Python 或本地服务器。由于 `file://` 没有可识别的应用 Referer，
独立版不调用 Nominatim，避免匿名地址查询；可从附近景点中选择地点。明确景点或固定事件
地址仍可通过后端版解析。实际后端保留共享缓存和 Nominatim 限流。

独立版对成功响应缓存 15 分钟，每次请求最多等待 25 秒；缓存、网络失败和合成示例分别标注。
停止仅停止客户端等待，不承诺上游服务或后端已经停止执行。用户文本通过 `textContent` 展示，
外链只允许 HTTP(S)。查询地址来自固定供应商，不接受任意网页 URL。

当前云环境没有可用的共享桌面/端口转发工具，打开浏览器的请求没有在用户界面显示。
此外，该实例的地图域名出站访问仍被策略拒绝。下载版在用户自己的浏览器中执行请求，
不改变云实例的访问策略；用户网络或服务 CORS 拒绝时仍会显示失败。

本次环境 ID 为 `ccarenv_b64_Y2NhcmVudl9kMDdiMDc4MmY2YjQ4MTkxOWJjN2EwMWVhMmZmZWEwNw`。
状态返回 `capabilities=[]`，没有提供 `cua_repl.js`；浏览器面板打开请求返回 queued，用户反馈未显示。

## 后端工具契约

`GET /api/tools` 返回工具描述和 Pydantic JSON Schema。没有模型参与执行。

| POST 接口 | 输入 | 主要输出 |
| --- | --- | --- |
| `/api/tools/city` | `destination` | `location`、`timezone` |
| `/api/tools/place` | `destination`、`name` | 地点坐标、`opening_hours_raw`、`website`、来源 |
| `/api/tools/attractions` | `center: Location`，必须有坐标 | 附近地点列表 |
| `/api/tools/routes` | `locations: Location[]`，2–20 个不同 ID，必须有坐标 | 有方向的 `travel_times`，单位为向上取整的分钟 |

所有成功输出包含 `tool`、`data_mode=live`、`data`、`research_steps`。
输入结构错误返回 422；供应商失败返回 503 和已有来源记录；未知工具返回 404。
示例请求：

```json
{"destination": "Chicago", "name": "Art Institute of Chicago"}
```

工具接口只收集数据，不改动固定事件，也不排程。原来的 `/api/plan` 和 `/validate` 继续独立工作。
地点 `cross_checked=false`、`website_checked=false`；`ticket_price` 和 `hotel_availability` 保持 null。
路线 `mode=driving`、`live_traffic=false`；`distance_meters=null`，尚未查询道路距离。

## 本次新增文件职责

| 文件 | 职责 |
| --- | --- |
| `src/backend/app/services/toolbox.py` | 四个有类型的工具输入、目录、调用分发和事实输出，不包含规划算法 |
| `src/frontend/tools.html` | 中文工作台结构 |
| `src/frontend/static/tools.css` | 桌面和手机样式 |
| `src/frontend/static/tools.js` | 查询交互、证据展示、离线示例；独立版包含三个公开 API 的浏览器适配 |
| `scripts/export_tools.py` | 将上述 HTML/CSS/JS 打包为独立 HTML 和确定性的 ZIP，无第三方依赖 |
| `docs/travel-tools.html`、`.zip` | 生成产物；修改源文件后重新打包，避免直接修改 |
| `tests/test_toolbox.py` | 注入供应商的接口测试，检查事实/未知值/方向/输入边界/失败证据 |
| `scripts/smoke_tools.py` | Chromium 交互检查；公开 HTTP 用假响应，覆盖独立版和后端示例 |

## 明确留待后续的工作

- 场馆官网页面获取、营业时间与官网证据的独立交叉核实。
- 票价、币种、适用日期/人群、订票政策的结构化提取。
- 酒店库存、房价及取消条款；需要选定供应商和真实报价权限。
- 步行、公交、道路距离、实时交通。
- 将这些有来源的事实交给候选排程器或未来模型。

Nominatim 和 Overpass 都来自 OSM，二者结果一致不能算独立交叉确认。
本轮没有连接通用网页搜索或 HTML 爬虫，也没有访问网站标签中的场馆官网。
