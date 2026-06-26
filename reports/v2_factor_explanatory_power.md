# V2 因子解释力逐项说明

### 中国铝业｜al_spread_q_mean
- 经济含义：季度平均铝氧价差
- 数据：SHFE AL/AO；质量：中；proxy：False
- 系数/标准化系数：3.1606148589031045 / 0.4744833679451793；单变量R²：0.2251344664566004
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜alumina_price_q_mean
- 经济含义：季度均价氧化铝
- 数据：SHFE AO；质量：中；proxy：False
- 系数/标准化系数：4.374772378932361 / 0.12764188033624946；单变量R²：0.016292449615773426
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜demand_score_q_mean
- 经济含义：综合需求状态
- 数据：真实PMI/部分真实API+默认代理；质量：低至中；proxy：False
- 系数/标准化系数：8.533094241834045 / 0.8089716870563933；单变量R²：0.6544351904588672
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜last_announced_q_profit_bn
- 经济含义：最近已公告利润
- 数据：公告日约束财报；质量：中高；proxy：False
- 系数/标准化系数：-6.813484351759216 / -0.037497131823899084；单变量R²：0.0014060348950188655
- 分级：UNSTABLE。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜ttm_announced_profit_bn
- 经济含义：已公告TTM利润
- 数据：公告日约束财报；质量：中高；proxy：False
- 系数/标准化系数：-3.276361868859481 / 0.4867274281912631；单变量R²：0.23690358935368117
- 分级：UNSTABLE。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜last_2q_avg_profit_bn
- 经济含义：近两季均值
- 数据：公告日约束财报；质量：中高；proxy：False
- 系数/标准化系数：7.647100216518526 / 0.29579841786245803；单变量R²：0.08749670400993333
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜is_q1
- 经济含义：Q1虚拟变量
- 数据：日历；质量：高；proxy：False
- 系数/标准化系数：0.829205502435441 / 0.36295478272463755；单变量R²：0.13173617430268886
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜is_q2
- 经济含义：Q2虚拟变量
- 数据：日历；质量：高；proxy：False
- 系数/标准化系数：3.893527190937543 / 0.15838859324792604；单变量R²：0.02508694647105696
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜is_q3
- 经济含义：Q3虚拟变量
- 数据：日历；质量：高；proxy：False
- 系数/标准化系数：-0.13603906415579498 / -0.1698053100717344；单变量R²：0.028833843328557866
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜is_q4
- 经济含义：Q4虚拟变量
- 数据：日历；质量：高；proxy：False
- 系数/标准化系数：-4.586693629217533 / -0.35153806590082914；单变量R²：0.12357901177729569
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜selected_k
- 经济含义：训练窗内部选择的氧化铝成本权重
- 数据：V2.3候选窗口；质量：中；proxy：False
- 系数/标准化系数：nan / nan；单变量R²：nan
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 中国铝业｜power_cost_proxy
- 经济含义：电力成本代理
- 数据：缺真实电价；质量：低；proxy：True
- 系数/标准化系数：nan / nan；单变量R²：nan
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

### 中国铝业｜anode_cost_proxy
- 经济含义：阳极成本代理
- 数据：缺真实阳极价格；质量：低；proxy：True
- 系数/标准化系数：nan / nan；单变量R²：nan
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

### 中国铝业｜primary_al_volume
- 经济含义：原铝产量
- 数据：缺strict数据；质量：低；proxy：True
- 系数/标准化系数：nan / nan；单变量R²：nan
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

### 中国铝业｜alumina_external_sales
- 经济含义：氧化铝外销量
- 数据：缺strict数据；质量：低；proxy：True
- 系数/标准化系数：nan / nan；单变量R²：nan
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

### 紫金矿业｜cu_au_revenue_index
- 经济含义：铜金价格×strict产量收入环境
- 数据：SHFE铜+SGE Au99.99+PDF strict产量；质量：中高；proxy：False
- 系数/标准化系数：4.96100817674622 / 0.9676759536837832；单变量R²：0.9449295732121918
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 紫金矿业｜revenue_x_demand
- 经济含义：收入环境×需求状态
- 数据：收入指数+需求分数；质量：低至中；proxy：True
- 系数/标准化系数：0.6315128791617975 / 0.01679191417928212；单变量R²：0.053111142209267596
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

### 紫金矿业｜is_q4
- 经济含义：Q4虚拟变量
- 数据：日历；质量：高；proxy：False
- 系数/标准化系数：-15.739643472699834 / -0.1492390660735425；单变量R²：0.008860549478748956
- 分级：MEDIUM。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 紫金矿业｜cu_price
- 经济含义：铜价工业金属景气
- 数据：SHFE铜；质量：中；proxy：False
- 系数/标准化系数：nan / nan；单变量R²：0.8691894434138919
- 分级：UNSTABLE。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 紫金矿业｜au_price_rmb_g
- 经济含义：金价人民币计价
- 数据：SGE Au99.99；质量：中高；proxy：False
- 系数/标准化系数：nan / nan；单变量R²：0.9431751837776601
- 分级：UNSTABLE。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 紫金矿业｜cu_ton
- 经济含义：矿产铜
- 数据：PDF strict；质量：高；proxy：False
- 系数/标准化系数：nan / nan；单变量R²：0.06846984449481848
- 分级：UNSTABLE。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 紫金矿业｜au_kg
- 经济含义：矿产金
- 数据：PDF strict；质量：高；proxy：False
- 系数/标准化系数：nan / nan；单变量R²：0.8296448681607356
- 分级：UNSTABLE。未做 ablation/permutation（本轮禁止重训）。
- 使用：保留并持续审计

### 紫金矿业｜cu_demand_score
- 经济含义：铜需求子分数
- 数据：真实库存/PMI+部分代理；质量：低至中；proxy：True
- 系数/标准化系数：nan / nan；单变量R²：nan
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

### 紫金矿业｜au_demand_score
- 经济含义：黄金需求子分数
- 数据：名义利率代理/部分默认代理；质量：低；proxy：True
- 系数/标准化系数：nan / nan；单变量R²：nan
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

### 紫金矿业｜demand_score
- 经济含义：铜金加权需求分数
- 数据：混合；质量：低至中；proxy：True
- 系数/标准化系数：nan / nan；单变量R²：0.0037941091059096417
- 分级：PROXY_ONLY。未做 ablation/permutation（本轮禁止重训）。
- 使用：仅研究用途，优先替换为真实数据

