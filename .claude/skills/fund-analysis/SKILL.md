# fund-analysis

> Use this skill when the user asks about fund (基金) analysis, sector (板块) performance, fund recommendations, ETF analysis, OTC fund (场外基金) rankings, or any task requiring real-time fund market data from 东方财富/天天基金. Trigger when: user mentions 基金, 板块, ETF, 场外基金, 基金排行, 基金推荐, 行业基金, 基金涨幅, fund screening, sector analysis, or wants to compare/evaluate funds. Do NOT trigger for stock (股票) analysis, forex, crypto, or general financial advice unrelated to funds.

# 核心原则

- **数据驱动**：所有分析必须基于实时API数据，不做无依据的推测
- **精准引用**：报告末尾必须标注数据来源（API接口名称+调用时间）
- **风险提示**：涨幅过高的板块必须标注追高风险
- **场外优先**：默认分析场外可购买的基金（ETF联接基金、开放式基金），而非场内ETF

---

# API接口大全

以下所有接口已在之前会话中验证可用。调用时必须设置 HTTP Header：
```
Referer: https://fund.eastmoney.com/
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36
```

## 1. 行业板块涨幅排行（东方财富行情中心）

**用途**：获取A股行业板块实时涨跌幅排名，是判断板块强弱的核心数据源。

**接口**：
```
GET https://push2.eastmoney.com/api/qt/clist/get
```

**参数**：
| 参数 | 值 | 说明 |
|------|------|------|
| pn | 1 | 页码 |
| pz | 50 | 每页条数（可调大至200） |
| po | 1 | 排序方向：1=降序 |
| np | 1 | 未知（固定1） |
| fltt | 2 | 数据格式（固定2） |
| invt | 2 | 未知（固定2） |
| fid | f3 | 排序字段：f3=涨跌幅 |
| fs | m:90+t:2+f:!50 | 行业板块筛选条件 |
| fields | f1,f2,f3,f4,f6,f12,f14,f62,f104,f105,f106,f108,f109,f112,f113,f114,f115,f128,f136,f140,f141,f152 | 返回字段 |

**字段含义**：
| 字段 | 含义 |
|------|------|
| f12 | 板块代码 |
| f14 | 板块名称 |
| f2 | 最新价 |
| f3 | 涨跌幅(%) |
| f4 | 涨跌额 |
| f6 | 成交额(元) |
| f104 | 涨家数 |
| f105 | 跌家数 |
| f62 | 主力净流入(元) |
| f128 | 换手率(%) |
| f136 | 量比 |
| f140 | PE(动态) |
| f141 | PB |
| f152 | 总市值(元) |

**Python调用示例**：
```python
import requests, json

url = "https://push2.eastmoney.com/api/qt/clist/get"
params = {
    "pn": "1", "pz": "50", "po": "1", "np": "1", "fltt": "2", "invt": "2",
    "fid": "f3", "fs": "m:90+t:2+f:!50",
    "fields": "f1,f2,f3,f4,f6,f12,f14,f62,f104,f105,f106,f108,f109,f112,f113,f114,f115,f128,f136,f140,f141,f152"
}
headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
r = requests.get(url, params=params, headers=headers, timeout=10)
data = r.json()
for item in data["data"]["diff"]:
    print(f"{item['f14']} | 涨幅:{item['f3']}% | 涨:{item.get('f104',0)} 跌:{item.get('f105',0)} | 主力净流入:{item.get('f62',0)}")
```

---

## 2. 基金涨幅排行（天天基金排名API）

**用途**：获取各类基金按不同时间维度的涨幅排名，是基金筛选的核心数据源。

**接口**：
```
GET https://api.fund.eastmoney.com/FundRankIndex.aspx
```

**参数**：
| 参数 | 值 | 说明 |
|------|------|------|
| f | 1c | 基金类型：1c=股票型, 1z=指数型, 1h=混合型, 1q=债券型, 1e=QDII, 1d=保本型, 1g=FOF |
| zd | 1m | 涨幅维度：1m=近1月, 3m=近3月, 6m=近6月, 1y=近1年, 2y=近2年, 3y=近3年 |
| sc | 1nnf | 排序字段：1nnf=近N月涨幅 |
| st | desc | 排序方向：desc=降序 |
| pi | 1 | 页码 |
| pn | 50 | 每页条数 |
| dx | 1 | 未知（固定1） |
| sd | 2025-05-05 | 起始日期（格式YYYY-MM-DD） |
| ed | 2025-06-04 | 结束日期（格式YYYY-MM-DD） |
| callback | (空) | JSONP回调，留空返回纯JSON |

**f参数对照表（基金类型）**：
| 值 | 类型 |
|------|------|
| 1c | 股票型基金 |
| 1z | 指数型基金（含ETF联接） |
| 1h | 混合型基金 |
| 1q | 债券型基金 |
| 1e | QDII基金 |
| 1d | 保本型基金 |
| 1g | FOF基金 |

**zd参数对照表（时间维度）**：
| 值 | 含义 |
|------|------|
| 1m | 近1月 |
| 3m | 近3月 |
| 6m | 近6月 |
| 1y | 近1年 |
| 2y | 近2年 |
| 3y | 近3月 |

**Python调用示例**：
```python
import requests, json
from datetime import datetime, timedelta

today = datetime.now().strftime("%Y-%m-%d")
month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

url = "https://api.fund.eastmoney.com/FundRankIndex.aspx"
params = {
    "f": "1z",  # 指数型基金（含ETF联接）
    "zd": "1m",  # 近1月涨幅
    "sc": "1nnf",
    "st": "desc",
    "pi": 1,
    "pn": 50,
    "dx": 1,
    "sd": month_ago,
    "ed": today,
    "callback": ""
}
headers = {"Referer": "https://fund.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
r = requests.get(url, params=params, headers=headers, timeout=10)
# 返回格式为JSON，解析后获取基金列表
data = r.json()
```

---

## 3. ETF联接基金排行（东方财富行情中心）

**用途**：获取场外ETF联接基金实时涨幅排名，是场外投资者购买板块基金最直接的方式。

**接口**：
```
GET https://push2.eastmoney.com/api/qt/clist/get
```

**参数**：
| 参数 | 值 | 说明 |
|------|------|------|
| pn | 1 | 页码 |
| pz | 100 | 每页条数 |
| po | 1 | 排序方向：1=降序 |
| np | 1 | 固定1 |
| fltt | 2 | 固定2 |
| invt | 2 | 固定2 |
| fid | f3 | 排序字段：f3=涨跌幅 |
| fs | b:MK0021,MK0022,MK0023,MK0024,MK0025,MK0026,MK0027,MK0028,MK0029,MK0030,MK0031,MK0032,MK0033,MK0034,MK0035,MK0036,MK0037,MK0038,MK0039,MK0040,MK0041 | ETF联接基金板块筛选 |
| fields | f1,f2,f3,f4,f6,f12,f14,f62,f104,f105,f106,f108,f109,f112,f113,f114,f115,f128,f136,f140,f141,f152 | 返回字段 |

**fs参数 - 常用板块代码对照表**：
| 代码 | 板块 |
|------|------|
| MK0021 | 医药 |
| MK0022 | 消费 |
| MK0023 | 科技 |
| MK0024 | 金融 |
| MK0025 | 地产 |
| MK0026 | 军工 |
| MK0027 | 新能源 |
| MK0028 | 半导体 |
| MK0029 | 互联网 |
| MK0030 | 新能源车 |
| MK0031 | 有色金属 |
| MK0032 | 农业 |
| MK0033 | 传媒 |
| MK0034 | 环保 |
| MK0035 | 基建 |
| MK0036 | 银行 |
| MK0037 | 证券 |
| MK0038 | 保险 |
| MK0039 | 钢铁 |
| MK0040 | 煤炭 |
| MK0041 | 石油 |

**Python调用示例**：
```python
import requests, json

url = "https://push2.eastmoney.com/api/qt/clist/get"
params = {
    "pn": "1", "pz": "100", "po": "1", "np": "1", "fltt": "2", "invt": "2",
    "fid": "f3",
    "fs": "b:MK0021,MK0022,MK0023,MK0024,MK0026,MK0027,MK0028,MK0029,MK0030",
    "fields": "f1,f2,f3,f4,f6,f12,f14"
}
headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
r = requests.get(url, params=params, headers=headers, timeout=10)
data = r.json()
for item in data["data"]["diff"]:
    print(f"{item['f14']} | 代码:{item['f12']} | 涨幅:{item['f3']}%")
```

---

## 4. 基金详情（天天基金）

**用途**：获取单只基金的详细信息，包括净值、涨幅、费率、持仓等。

**接口**：
```
GET https://fund.eastmoney.com/pingzhongdata/{基金代码}.js
```

**参数**：基金代码直接拼入URL，如 `110011.js`

**返回内容**：JavaScript变量赋值语句，包含：
- `fS_name` — 基金名称
- `fS_code` — 基金代码
- `Data_netWorthTrend` — 净值走势数据（日期+净值数组）
- `Data_ACWorthTrend` — 累计净值走势
- `Data_grandTotal` — 总涨幅数据
- `Data_rateInSimilarType` — 同类排名数据
- `Data_rateInSimilarPers498` — 近1月/3月/6月/1年/2年/3年涨幅
- `Data_fluctuationScale` — 规模变动
- `Data_currentFundManager` — 基金经理信息
- `Data_holdings` — 持仓数据
- `Data_stockHoldings` — 股票持仓

**Python调用示例**：
```python
import requests, re, json

fund_code = "110011"
url = f"https://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
headers = {"Referer": "https://fund.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers, timeout=10)
text = r.text

# 提取基金名称
name_match = re.search(r'var fS_name\s*=\s*"([^"]+)"', text)
# 提取近N月涨幅数据
rate_match = re.search(r'var Data_rateInSimilarPers498\s*=\s*(\[.*?\]);', text)
if rate_match:
    rates = json.loads(rate_match.group(1))
    # rates格式: [[近1月涨幅,排名],[近3月涨幅,排名],...]
```

---

## 5. 基金实时估值（天天基金）

**用途**：获取基金盘中实时估值数据，适合交易时段查看。

**接口**：
```
GET https://fundgz.1234567.com.cn/js/{基金代码}.js
```

**参数**：基金代码直接拼入URL，如 `110011.js`

**返回格式**：JSONP回调
```javascript
jsonpgz({"fundcode":"110011","name":"易方达中小盘混合","jzrq":"2025-06-03","dwjz":"3.5120","gsz":"3.5280","gszzl":"0.46","gztime":"2025-06-04 15:00"});
```

**字段含义**：
| 字段 | 含义 |
|------|------|
| fundcode | 基金代码 |
| name | 基金名称 |
| jzrq | 净值日期 |
| dwjz | 单位净值 |
| gsz | 估算净值 |
| gszzl | 估算涨幅(%) |
| gztime | 估值时间 |

**Python调用示例**：
```python
import requests, re, json

fund_code = "110011"
url = f"https://fundgz.1234567.com.cn/js/{fund_code}.js"
headers = {"Referer": "https://fund.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
r = requests.get(url, headers=headers, timeout=10)
# 解析JSONP
match = re.search(r'jsonpgz\((.*?)\)', r.text)
if match:
    data = json.loads(match.group(1))
    print(f"{data['name']} | 估值:{data['gsz']} | 涨幅:{data['gszzl']}% | 时间:{data['gztime']}")
```

---

## 6. 基金搜索（天天基金）

**用途**：根据关键词搜索基金代码和名称，用于基金名称→代码的转换。

**接口**：
```
GET https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx
```

**参数**：
| 参数 | 值 | 说明 |
|------|------|------|
| m | 1 | 固定1 |
| key | 医药 | 搜索关键词（基金名称/代码片段） |
| IsNeedBaseInfo | 0 | 是否需要基础信息 |
| IsNeedZTInfo | 0 | 是否需要涨跌信息 |
| t | 1 | 固定1 |
| c | (空) | callback |
| pageindex | 0 | 页码 |
| pagesize | 20 | 每页条数 |

**Python调用示例**：
```python
import requests, json

url = "https://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
params = {
    "m": "1", "key": "医药", "IsNeedBaseInfo": "0", "IsNeedZTInfo": "0",
    "t": "1", "c": "", "pageindex": "0", "pagesize": "20"
}
headers = {"Referer": "https://fund.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
r = requests.get(url, params=params, headers=headers, timeout=10)
# 返回JSONP格式，需解析
```

---

## 7. 行业板块K线数据（东方财富）

**用途**：获取行业板块的历史K线数据，用于趋势分析和判断追高风险。

**接口**：
```
GET https://push2his.eastmoney.com/api/qt/stock/kline/get
```

**参数**：
| 参数 | 值 | 说明 |
|------|------|------|
| secid | 90.BK0473 | 板块代码（90.前缀+板块代码，板块代码从API1获取的f12字段） |
| fields1 | f1,f2,f3,f4,f5,f6 | 基础字段 |
| fields2 | f51,f52,f53,f54,f55,f56,f57 | K线字段 |
| klt | 101 | K线周期：101=日K, 102=周K, 103=月K |
| fqt | 1 | 复权：1=前复权 |
| beg | 20250501 | 起始日期 |
| end | 20250604 | 结束日期 |

**fields2字段含义**：
| 字段 | 含义 |
|------|------|
| f51 | 日期 |
| f52 | 开盘价 |
| f53 | 收盘价 |
| f54 | 最高价 |
| f55 | 最低价 |
| f56 | 成交量 |
| f57 | 成交额 |

**Python调用示例**：
```python
import requests, json

url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
params = {
    "secid": "90.BK0473",  # 板块代码
    "fields1": "f1,f2,f3,f4,f5,f6",
    "fields2": "f51,f52,f53,f54,f55,f56,f57",
    "klt": "101",  # 日K
    "fqt": "1",
    "beg": "20250501",
    "end": "20250604"
}
headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
r = requests.get(url, params=params, headers=headers, timeout=10)
data = r.json()
klines = data.get("data", {}).get("klines", [])
for kline in klines:
    parts = kline.split(",")
    print(f"日期:{parts[0]} 开:{parts[1]} 收:{parts[2]} 高:{parts[3]} 低:{parts[4]} 量:{parts[5]}")
```

---

## 8. 基金持仓数据（天天基金）

**用途**：获取基金最新持仓的股票明细，用于分析基金实际投向。

**接口**：
```
GET https://fund.eastmoney.com/api/FundArchivesDatas.aspx
```

**参数**：
| 参数 | 值 | 说明 |
|------|------|------|
| type | jjhhold | 数据类型：jjhhold=持仓 |
| fundcode | 110011 | 基金代码 |
| topline | 10 | 返回条数 |
| year | 2025 | 年份 |
| month | 3 | 季度月份：3/6/9/12 |

---

# 工作流

当用户请求基金分析时，按以下步骤执行：

## Step 1: 明确分析范围

确认用户需求：
- 分析哪些板块？（全部行业 / 指定行业）
- 时间维度？（近1月 / 近3月 / 近1年）
- 基金类型？（股票型 / 指数型 / 混合型 / ETF联接）
- 默认值：全部行业 + 近1月 + 指数型（含ETF联接）

## Step 2: 获取行业板块涨幅

调用 **API1（行业板块涨幅排行）**，获取行业板块实时涨跌幅排名。

```python
# 使用API1获取行业板块涨幅
# 按f3（涨跌幅）降序排列
# 输出：板块名称、涨跌幅、涨跌家数、主力净流入
```

## Step 3: 获取基金排行数据

根据需求调用 **API2（基金涨幅排行）**：
- 场外板块基金 → `f=1z`（指数型，含ETF联接）
- 主动管理型 → `f=1c`（股票型）
- 混合型 → `f=1h`

```python
# 使用API2获取基金排行
# zd参数按用户需求设置时间维度
# sd/ed参数按实际日期计算
```

## Step 4: 获取板块K线数据（可选）

对涨幅靠前的板块，调用 **API7（行业板块K线）** 获取近期走势，判断：
- 是否连续上涨（追高风险）
- 是否回调到位（买入机会）
- 趋势是否健康（量价配合）

## Step 5: 获取基金详情（可选）

对重点基金，调用 **API4（基金详情）** 或 **API5（实时估值）** 获取：
- 净值走势
- 同类排名
- 持仓明细
- 基金经理信息

## Step 6: 生成分析报告

输出格式如下：

### 📊 板块涨幅排名

| 排名 | 板块 | 涨幅(%) | 涨家数 | 跌家数 | 主力净流入(亿) |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | XX板块 | +X.XX | XX | XX | +X.XX |

### 🏆 板块代表性基金

| 基金代码 | 基金名称 | 近1月(%) | 近3月(%) | 近1年(%) | 基金类型 |
|:---:|:---:|:---:|:---:|:---:|:---:|
| XXXXXX | XX基金 | +X.XX | +X.XX | +X.XX | 指数型 |

### ⚠️ 风险提示

- 🔴 **高风险板块**：近X日连续上涨X%+，短期追高风险较大
- 🟡 **中等风险**：上涨趋势确立但涨幅适中
- 🟢 **低风险**：回调到位或底部区域

### 📋 数据来源

| 数据项 | API接口 | 调用时间 |
|:---:|:---:|:---:|
| 行业板块涨幅 | push2.eastmoney.com/api/qt/clist/get | YYYY-MM-DD HH:MM |
| 基金排行 | api.fund.eastmoney.com/FundRankIndex.aspx | YYYY-MM-DD HH:MM |

---

# 注意事项

1. **日期计算**：API2的sd/ed参数需要根据当前日期动态计算，不要硬编码
2. **交易时间**：API5（实时估值）仅在交易日 9:30-15:00 有数据，非交易时间返回上一交易日数据
3. **JSONP解析**：部分接口返回JSONP格式（带callback包裹），需去除callback前缀后解析JSON
4. **频率限制**：东方财富API无严格频率限制，但建议每次调用间隔 > 0.5秒
5. **字段缺失**：部分基金可能缺少某些字段值，代码中需做 `.get(key, "N/A")` 处理
6. **板块代码映射**：API1返回的f12（板块代码）可用于API7的secid参数，格式为 `90.{f12}`
7. **基金类型筛选**：API2的f参数是最重要的筛选条件，务必根据用户需求选择正确的类型
8. **涨幅单位**：API返回的涨跌幅值已经是百分比数值（如 5.23 表示 5.23%），不需要再除以100
