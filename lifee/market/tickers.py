"""
静态映射表：中英文公司名/缩写 → yfinance ticker

覆盖：美股 Top 50、港股 Top 30、A股 Top 50
"""

# fmt: off
TICKER_MAP: dict[str, str] = {
    # ============ 美股 Top 50 ============
    # Apple
    "苹果": "AAPL", "apple": "AAPL", "aapl": "AAPL",
    # Microsoft
    "微软": "MSFT", "microsoft": "MSFT", "msft": "MSFT",
    # Google / Alphabet
    "谷歌": "GOOGL", "google": "GOOGL", "alphabet": "GOOGL", "googl": "GOOGL",
    # Amazon
    "亚马逊": "AMZN", "amazon": "AMZN", "amzn": "AMZN",
    # NVIDIA
    "英伟达": "NVDA", "nvidia": "NVDA", "nvda": "NVDA",
    # Meta
    "meta": "META", "脸书": "META", "facebook": "META",
    # Tesla
    "特斯拉": "TSLA", "tesla": "TSLA", "tsla": "TSLA",
    # Berkshire Hathaway
    "伯克希尔": "BRK-B", "berkshire": "BRK-B", "brk": "BRK-B",
    # JPMorgan
    "摩根大通": "JPM", "jpmorgan": "JPM", "jpm": "JPM",
    # Visa
    "visa": "V",
    # UnitedHealth
    "联合健康": "UNH", "unitedhealth": "UNH",
    # Johnson & Johnson
    "强生": "JNJ", "johnson": "JNJ", "jnj": "JNJ",
    # Walmart
    "沃尔玛": "WMT", "walmart": "WMT", "wmt": "WMT",
    # Mastercard
    "万事达": "MA", "mastercard": "MA",
    # Procter & Gamble
    "宝洁": "PG", "procter": "PG", "pg": "PG",
    # Eli Lilly
    "礼来": "LLY", "eli lilly": "LLY", "lilly": "LLY",
    # Home Depot
    "家得宝": "HD", "home depot": "HD",
    # Broadcom
    "博通": "AVGO", "broadcom": "AVGO", "avgo": "AVGO",
    # Chevron
    "雪佛龙": "CVX", "chevron": "CVX",
    # Merck
    "默克": "MRK", "默沙东": "MRK", "merck": "MRK",
    # Coca-Cola
    "可口可乐": "KO", "coca-cola": "KO", "coca cola": "KO", "ko": "KO",
    # Costco
    "好市多": "COST", "costco": "COST",
    # PepsiCo
    "百事": "PEP", "百事可乐": "PEP", "pepsi": "PEP", "pepsico": "PEP",
    # Adobe
    "adobe": "ADBE", "adbe": "ADBE",
    # Netflix
    "奈飞": "NFLX", "netflix": "NFLX", "nflx": "NFLX",
    # AMD
    "amd": "AMD",
    # Intel
    "英特尔": "INTC", "intel": "INTC", "intc": "INTC",
    # Salesforce
    "salesforce": "CRM", "crm": "CRM",
    # Cisco
    "思科": "CSCO", "cisco": "CSCO",
    # Oracle
    "甲骨文": "ORCL", "oracle": "ORCL",
    # Disney
    "迪士尼": "DIS", "disney": "DIS",
    # Nike
    "耐克": "NKE", "nike": "NKE",
    # McDonald's
    "麦当劳": "MCD", "mcdonald": "MCD",
    # IBM
    "ibm": "IBM",
    # Goldman Sachs
    "高盛": "GS", "goldman sachs": "GS", "goldman": "GS",
    # Morgan Stanley
    "摩根士丹利": "MS", "morgan stanley": "MS",
    # Boeing
    "波音": "BA", "boeing": "BA",
    # Qualcomm
    "高通": "QCOM", "qualcomm": "QCOM",
    # Caterpillar
    "卡特彼勒": "CAT", "caterpillar": "CAT",
    # Starbucks
    "星巴克": "SBUX", "starbucks": "SBUX",
    # American Express
    "美国运通": "AXP", "american express": "AXP", "amex": "AXP",
    # 3M
    "3m": "MMM",
    # PayPal
    "paypal": "PYPL",
    # Uber
    "uber": "UBER",
    # Airbnb
    "airbnb": "ABNB",
    # Snowflake
    "snowflake": "SNOW",
    # Palantir
    "palantir": "PLTR",
    # CrowdStrike
    "crowdstrike": "CRWD",
    # Block (Square)
    "block": "SQ", "square": "SQ",
    # TSMC (ADR)
    "台积电": "TSM", "tsmc": "TSM",
    # PDD (Pinduoduo)
    "拼多多": "PDD", "pinduoduo": "PDD", "pdd": "PDD",
    # Spotify
    "spotify": "SPOT",
    # Coinbase
    "coinbase": "COIN",
    # Rivian
    "rivian": "RIVN",
    # Lululemon
    "lululemon": "LULU",
    # ServiceNow
    "servicenow": "NOW",
    # Palo Alto Networks
    "palo alto": "PANW",
    # Arm Holdings
    "arm": "ARM",
    # Micron
    "美光": "MU", "micron": "MU",
    # Applied Materials
    "应用材料": "AMAT", "applied materials": "AMAT",
    # Lam Research
    "lam research": "LRCX",
    # Texas Instruments
    "德州仪器": "TXN", "texas instruments": "TXN",
    # Eli Lilly already listed, add Novo Nordisk
    "诺和诺德": "NVO", "novo nordisk": "NVO",
    # Berkshire already listed, add more financials
    "花旗": "C", "citigroup": "C",
    # Target
    "target": "TGT",
    # General Electric
    "通用电气": "GE", "ge": "GE",
    # Ford
    "福特": "F", "ford": "F",
    # General Motors
    "通用汽车": "GM", "gm": "GM",
    # Moderna
    "moderna": "MRNA",
    # Snowflake already listed, add Databricks parent
    # Zoom
    "zoom": "ZM",
    # Pinterest
    "pinterest": "PINS",
    # Snap
    "snap": "SNAP", "snapchat": "SNAP",
    # Reddit
    "reddit": "RDDT",
    # Duolingo
    "duolingo": "DUOL", "多邻国": "DUOL",
    # Super Micro
    "super micro": "SMCI", "supermicro": "SMCI",

    # ============ 港股 Top 30 ============
    # Tencent
    "腾讯": "0700.HK", "tencent": "0700.HK",
    # Alibaba HK
    "阿里巴巴": "9988.HK", "阿里": "9988.HK", "alibaba": "9988.HK",
    # Meituan
    "美团": "3690.HK", "meituan": "3690.HK",
    # JD.com
    "京东": "9618.HK", "jd": "9618.HK",
    # Baidu
    "百度": "9888.HK", "baidu": "9888.HK",
    # NetEase
    "网易": "9999.HK", "netease": "9999.HK",
    # Xiaomi
    "小米": "1810.HK", "xiaomi": "1810.HK",
    # BYD
    "比亚迪": "1211.HK", "byd": "1211.HK",
    # Li Auto
    "理想汽车": "2015.HK", "理想": "2015.HK", "li auto": "2015.HK",
    # XPeng
    "小鹏汽车": "9868.HK", "小鹏": "9868.HK", "xpeng": "9868.HK",
    # NIO
    "蔚来": "9866.HK", "nio": "9866.HK",
    # Kuaishou
    "快手": "1024.HK", "kuaishou": "1024.HK",
    # Bilibili
    "哔哩哔哩": "9626.HK", "b站": "9626.HK", "bilibili": "9626.HK",
    # HSBC
    "汇丰": "0005.HK", "hsbc": "0005.HK",
    # AIA
    "友邦保险": "1299.HK", "友邦": "1299.HK", "aia": "1299.HK",
    # China Mobile
    "中国移动": "0941.HK",
    # CNOOC
    "中海油": "0883.HK", "cnooc": "0883.HK",
    # Ping An
    "平安": "2318.HK", "中国平安": "2318.HK", "ping an": "2318.HK",
    # China Construction Bank
    "建设银行": "0939.HK", "建行": "0939.HK",
    # ICBC
    "工商银行": "1398.HK", "工行": "1398.HK", "icbc": "1398.HK",
    # Bank of China
    "中国银行": "3988.HK", "中行": "3988.HK",
    # Lenovo
    "联想": "0992.HK", "lenovo": "0992.HK",
    # Geely
    "吉利": "0175.HK", "吉利汽车": "0175.HK", "geely": "0175.HK",
    # Sunny Optical
    "舜宇光学": "2382.HK",
    # China Resources Beer
    "华润啤酒": "0291.HK",
    # Wuxi Biologics
    "药明生物": "2269.HK",
    # Trip.com
    "携程": "9961.HK", "trip.com": "9961.HK",
    # Zhongsheng Group
    "中升控股": "0881.HK",
    # Country Garden
    "碧桂园": "2007.HK",
    # Sands China
    "金沙中国": "1928.HK",
    # Alibaba US ADR
    "阿里美股": "BABA",
    # JD US ADR
    "京东美股": "JD",
    # Baidu US ADR
    "百度美股": "BIDU",
    # PDD US ADR already listed
    # Zhihu
    "知乎": "2390.HK",
    # Weimob
    "微盟": "2013.HK",
    # Pop Mart
    "泡泡玛特": "9992.HK",
    # Miniso
    "名创优品": "9896.HK", "miniso": "9896.HK",
    # Nongfu Spring
    "农夫山泉": "9633.HK",
    # Chow Tai Fook
    "周大福": "1929.HK",
    # Li Ning
    "李宁": "2331.HK", "li ning": "2331.HK",
    # Anta Sports
    "安踏": "2020.HK", "安踏体育": "2020.HK", "anta": "2020.HK",
    # China Mengniu
    "蒙牛": "2319.HK", "蒙牛乳业": "2319.HK",
    # Haidilao
    "海底捞": "6862.HK",

    # ============ A股 Top 50 ============
    # Kweichow Moutai
    "茅台": "600519.SS", "贵州茅台": "600519.SS", "moutai": "600519.SS",
    # CATL
    "宁德时代": "300750.SZ", "catl": "300750.SZ",
    # China Merchants Bank
    "招商银行": "600036.SS", "招行": "600036.SS",
    # Wuliangye
    "五粮液": "000858.SZ",
    # Ping An (A-share)
    "中国平安a": "601318.SS",
    # Industrial Bank
    "兴业银行": "601166.SS",
    # Midea
    "美的": "000333.SZ", "美的集团": "000333.SZ", "midea": "000333.SZ",
    # LONGi
    "隆基": "601012.SS", "隆基绿能": "601012.SS", "longi": "601012.SS",
    # BYD A-share
    "比亚迪a": "002594.SZ",
    # SMIC
    "中芯国际": "688981.SS", "中芯": "688981.SS", "smic": "688981.SS",
    # Foxconn Industrial
    "工业富联": "601138.SS",
    # China Yangtze Power
    "长江电力": "600900.SS",
    # PetroChina
    "中国石油": "601857.SS", "中石油": "601857.SS",
    # Sinopec
    "中国石化": "600028.SS", "中石化": "600028.SS",
    # ICBC A-share
    "工商银行a": "601398.SS",
    # Agricultural Bank
    "农业银行": "601288.SS", "农行": "601288.SS",
    # Bank of China A-share
    "中国银行a": "601988.SS",
    # China Life
    "中国人寿": "601628.SS",
    # Gree
    "格力": "000651.SZ", "格力电器": "000651.SZ", "gree": "000651.SZ",
    # Haier
    "海尔": "600690.SS", "海尔智家": "600690.SS", "haier": "600690.SS",
    # Sungrow
    "阳光电源": "300274.SZ",
    # East Money
    "东方财富": "300059.SZ",
    # NARI Technology
    "国电南瑞": "600406.SS",
    # Luxshare
    "立讯精密": "002475.SZ", "立讯": "002475.SZ",
    # Will Semiconductor
    "韦尔股份": "603501.SS",
    # Tongwei
    "通威": "600438.SS", "通威股份": "600438.SS",
    # Zijin Mining
    "紫金矿业": "601899.SS", "紫金": "601899.SS",
    # China Tourism Group Duty Free
    "中国中免": "601888.SS", "中免": "601888.SS",
    # Hengrui Medicine
    "恒瑞医药": "600276.SS", "恒瑞": "600276.SS",
    # WuXi AppTec
    "药明康德": "603259.SS",
    # Mindray
    "迈瑞医疗": "300760.SZ", "迈瑞": "300760.SZ",
    # Hikvision
    "海康威视": "002415.SZ", "海康": "002415.SZ", "hikvision": "002415.SZ",
    # iFlytek
    "科大讯飞": "002230.SZ", "讯飞": "002230.SZ",
    # Shenzhou International (A-share proxy: there's no direct A-share)
    # CRRC
    "中国中车": "601766.SS",
    # China Shenhua
    "中国神华": "601088.SS", "神华": "601088.SS",
    # Anhui Conch
    "海螺水泥": "600585.SS", "海螺": "600585.SS",
    # Ganfeng Lithium
    "赣锋锂业": "002460.SZ", "赣锋": "002460.SZ",
    # Tianqi Lithium
    "天齐锂业": "002466.SZ", "天齐": "002466.SZ",
    # Yili
    "伊利": "600887.SS", "伊利股份": "600887.SS",
    # Wanhua Chemical
    "万华化学": "600309.SS", "万华": "600309.SS",
    # Kweichow Moutai's neighbor
    "泸州老窖": "000568.SZ",
    # Foshan Haitian
    "海天味业": "603288.SS", "海天": "603288.SS",
    # CATL in Shenzhen is already listed above
    # China Telecom
    "中国电信": "601728.SS",
    # China Unicom
    "中国联通": "600050.SS",
    # Yangtze Optical Fibre
    "长飞光纤": "601869.SS",
    # SF Express
    "顺丰": "002352.SZ", "顺丰控股": "002352.SZ",
    # ZTE
    "中兴通讯": "000063.SZ", "中兴": "000063.SZ", "zte": "000063.SZ",
    # BOE
    "京东方": "000725.SZ", "boe": "000725.SZ",
    # Sany Heavy
    "三一重工": "600031.SS", "三一": "600031.SS",
}
# fmt: on
