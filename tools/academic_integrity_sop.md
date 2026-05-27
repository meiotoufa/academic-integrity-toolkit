# Academic Integrity SOP — 学术打假技能

> 投稿 Citation 幻觉检测 + 数据可疑分析 + 图片造假检测。三合一学术诚信审查工具。

---

## 一、适用场景

| 场景 | 触发方式 |
|---|---|
| 审稿时验证参考文献真实性 | "检查这篇论文的引用是否真实" |
| 审查数据是否存在统计造假 | "分析这组数据是否可疑" |
| 检测论文图片是否被PS/拼接/复用 | "检查这张图是否造假" |

---

## 二、前置依赖

```python
# 基础（标准库即可用）
import json, urllib.request, re, hashlib, struct, math, statistics, collections

# 图像分析需要（首次自动安装）
# pip install Pillow numpy
```

---

## 三、模块一：Citation 幻觉检测

### 3.1 原理

LLM 生成的论文常编造不存在的引用（幻觉 citation）。特征包括：
- DOI 不存在或指向其他论文
- 作者+标题+期刊+年份的组合在任何数据库中查不到
- 期刊名拼写错误或根本不存在
- 年份与作者活跃年代不符

### 3.2 验证流程（逐条引用执行）

```
Step 1: 提取 → 从论文中解析出所有引用条目
Step 2: DOI检查 → 有DOI的直接查CrossRef验证
Step 3: 标题搜索 → 无DOI的用标题在Semantic Scholar/CrossRef搜索
Step 4: 交叉验证 → 对比返回结果与原引用的作者/年份/期刊
Step 5: 标记 → 分级：✅已验证 / ⚠️存疑 / ❌幻觉
```

### 3.3 快速调用

```python
from academic_integrity_utils import check_citations

# 传入引用列表（每条是dict: title, authors, year, journal, doi）
refs = [
    {"title": "Attention Is All You Need", "authors": "Vaswani et al.", "year": 2017, "journal": "NeurIPS"},
    {"title": "A Fake Paper That Never Existed", "authors": "Nobody, A.", "year": 2023, "journal": "Fake Journal"},
]
results = check_citations(refs)
for r in results:
    print(f"[{r['status']}] {r['title']}")
    if r['status'] != '✅':
        print(f"  原因: {r['reason']}")
```

### 3.4 API 说明

| API | 用途 | 限制 |
|---|---|---|
| CrossRef (`api.crossref.org`) | DOI 验证 + 标题搜索 | 免费，礼貌池50req/s，加 `mailto` 提速 |
| Semantic Scholar (`api.semanticscholar.org`) | 标题/作者搜索 | 免费，100req/5min 无key |
| OpenAlex (`api.openalex.org`) | 备用验证源 | 免费，无限制 |

### 3.5 常见幻觉模式

| 模式 | 示例 | 检测方法 |
|---|---|---|
| 虚构标题 | 真实作者+编造标题 | 标题搜索返回0结果 |
| 张冠李戴 | 真实论文+错误作者 | 作者名不在返回结果中 |
| 期刊不存在 | "Journal of Advanced AI Studies" | 期刊名在ISSN数据库中查不到 |
| 年份错误 | 把2020年的论文标为2018 | CrossRef返回年份不匹配 |
| DOI格式错 | `10.xxxx/fake-suffix` | DOI解析返回404 |
| 自引幻觉 | 编造作者自己的论文 | 组合搜索返回0结果 |

---

## 四、模块二：数据可疑分析

### 4.1 统计检测方法

#### A. Benford 定律检测

自然产生的数据（人口、面积、财务数据、实验测量值）首位数字分布符合 Benford 定律：
P(d) = log10(1 + 1/d)。编造/篡改的数据往往不符合。

```python
from academic_integrity_utils import benford_test

data = [123, 456, 789, 234, 567, ...]  # 至少需要100+数据点
result = benford_test(data)
print(f"卡方统计量: {result['chi2']:.2f}, p值: {result['p_value']:.4f}")
print(f"判定: {result['verdict']}")  # PASS / SUSPICIOUS / FAIL
```

#### B. GRIM 测试（均值粒度检查）

对于整数Likert量表数据，报告的均值必须在数学上可能。例如 N=20 的 1-5 量表，均值只能是 X.X0 或 X.X5，报告 M=3.47 是不可能的。

```python
from academic_integrity_utils import grim_test

result = grim_test(mean=3.47, n=20, scale_min=1, scale_max=5)
print(f"数学上可能: {result['possible']}")  # False → 数据有问题
```

#### C. 重复值/模式检测

```python
from academic_integrity_utils import detect_data_anomalies

data = [1.23, 4.56, 1.23, 7.89, 4.56, 1.23, ...]
report = detect_data_anomalies(data)
print(f"重复率: {report['duplicate_ratio']:.1%}")
print(f"末位数字分布: {report['last_digit_uniformity']}")  # 应≈均匀
print(f"可疑模式: {report['suspicious_patterns']}")
```

#### D. 检测清单

| 检查项 | 原理 | 红旗 |
|---|---|---|
| Benford首位 | 自然数据符合log分布 | χ² p<0.01 |
| GRIM均值 | 整数数据均值有粒度限制 | 数学上不可能的均值 |
| 末位数字 | 应近似均匀分布 | 某个数字显著过多/过少 |
| 重复值 | 大样本中精确重复应罕见 | 重复率>期望值3倍 |
| 精度异常 | 同组数据精度应一致 | 有的3位小数有的7位 |
| p值堆积 | p值应均匀分布于(0,0.05) | 大量恰好<0.05的p值 |
| 效应量过大 | d>2.0 在社科中极罕见 | Cohen's d 异常大 |
| 完美相关 | r=1.000 几乎不可能 | 相关系数过于"干净" |

---

## 五、模块三：图片造假检测

### 5.1 检测技术

#### A. Error Level Analysis (ELA)

JPEG 重新压缩后，被修改区域的误差级别与原始区域不同。PS 过的区域在 ELA 图中会显著亮于周围。

```python
from academic_integrity_utils import ela_analysis

result = ela_analysis("figure1.jpg", quality=90)
# 保存ELA可视化图
result['ela_image'].save("figure1_ela.png")
print(f"最大误差区域: {result['hotspots']}")
print(f"整体评估: {result['verdict']}")
```

#### B. 元数据/EXIF 分析

```python
from academic_integrity_utils import check_image_metadata

meta = check_image_metadata("figure1.jpg")
print(f"创建软件: {meta['software']}")      # 如 'Adobe Photoshop'
print(f"修改历史: {meta['edit_history']}")
print(f"创建时间: {meta['create_date']}")
print(f"可疑标记: {meta['flags']}")          # 如 ['photoshop_edited', 'metadata_stripped']
```

#### C. 克隆/复制-移动检测

检测图像内是否有区域被复制粘贴（常见于 Western blot 造假）。

```python
from academic_integrity_utils import detect_clone_regions

result = detect_clone_regions("western_blot.png", block_size=16, threshold=0.95)
print(f"发现 {len(result['clone_pairs'])} 组克隆区域")
for pair in result['clone_pairs']:
    print(f"  区域A {pair['region_a']} ↔ 区域B {pair['region_b']}, 相似度: {pair['similarity']:.3f}")
```

#### D. 多图一致性检查

同一实验的多张图（如不同条件的条带）应有独立噪声模式。

```python
from academic_integrity_utils import compare_image_noise

result = compare_image_noise("panel_a.png", "panel_b.png")
print(f"噪声相关性: {result['noise_correlation']:.3f}")  # >0.8 高度可疑
print(f"判定: {result['verdict']}")
```

### 5.2 图片检测清单

| 检查项 | 方法 | 红旗 |
|---|---|---|
| ELA 不均匀 | JPEG重压缩差异 | 局部区域亮度异常高 |
| 元数据异常 | EXIF/XMP 检查 | Photoshop编辑标记、元数据被清空 |
| 克隆区域 | 块哈希匹配 | 图内存在高度相似的不同区域 |
| 噪声不一致 | 高频分量分析 | 拼接图的不同区域噪声模式不同 |
| 分辨率不匹配 | DPI/像素密度 | 同图不同部分分辨率不同 |
| 边缘伪影 | 梯度分析 | 粘贴区域边缘有锐利过渡 |
| 直方图断裂 | 亮度直方图 | 拼接导致的多峰或断口 |

---

## 六、完整审查流程

```
┌─────────────────────────────────────────────────┐
│  1. 收集材料                                      │
│     ├─ 论文PDF/文本                                │
│     ├─ 数据表（如有）                               │
│     └─ 图片文件                                    │
├─────────────────────────────────────────────────┤
│  2. Citation 检查                                  │
│     ├─ 提取引用列表                                 │
│     ├─ 逐条验证（CrossRef + Semantic Scholar）       │
│     └─ 标记 ✅⚠️❌                                 │
├─────────────────────────────────────────────────┤
│  3. 数据分析（如有原始数据）                          │
│     ├─ Benford 定律                                │
│     ├─ GRIM 测试                                   │
│     ├─ 重复值/末位数字                               │
│     └─ p值分布/效应量                                │
├─────────────────────────────────────────────────┤
│  4. 图片检查                                       │
│     ├─ ELA 分析                                    │
│     ├─ 元数据检查                                   │
│     ├─ 克隆检测                                     │
│     └─ 噪声一致性                                   │
├─────────────────────────────────────────────────┤
│  5. 综合报告                                       │
│     ├─ 分模块汇总发现                                │
│     ├─ 按严重度排序                                  │
│     └─ 给出 PASS / SUSPICIOUS / FAIL               │
└─────────────────────────────────────────────────┘
```

---

## 七、输出报告格式

```markdown
# 学术诚信审查报告

## 基本信息
- 论文: <标题>
- 审查时间: <日期>
- 审查范围: Citation / Data / Image（勾选适用项）

## 总体判定
PASS / SUSPICIOUS / FAIL

## Citation 审查
| # | 引用 | DOI | 验证结果 | 备注 |
|---|---|---|---|---|
| 1 | Vaswani et al., 2017 | 10.xxx | ✅ | - |
| 2 | Fake et al., 2023 | - | ❌ 幻觉 | 标题/期刊均不存在 |

幻觉率: X/Y (Z%)

## 数据审查
| 检查项 | 结果 | 详情 |
|---|---|---|
| Benford首位 | ⚠️ | χ²=18.3, p=0.019 |
| GRIM测试 | ❌ | Table 2, M=3.47, N=20 不可能 |

## 图片审查
| 图片 | ELA | 元数据 | 克隆 | 判定 |
|---|---|---|---|---|
| Fig.1 | 正常 | 无异常 | 无 | ✅ |
| Fig.3a | 局部异常 | PS编辑 | 2处 | ❌ |

## 关键发现（按严重度）
1. **[CRITICAL]** Fig.3a 存在克隆区域...
2. **[HIGH]** 3条引用为幻觉...
3. **[MEDIUM]** Table 2 均值不通过GRIM...
```

---

## 八、注意事项

1. **假阳性控制**：单一检测手段不足以定性，至少两种方法交叉验证才标记 FAIL
2. **JPEG伪影**：多次压缩的JPEG会产生类ELA异常，不一定是PS，需结合元数据判断
3. **Benford局限**：对范围受限的数据（如年龄18-25）不适用
4. **GRIM局限**：仅适用于整数量表数据的均值检验
5. **API速率**：CrossRef 建议加 `mailto` 参数进入 polite pool；Semantic Scholar 5min 100次
6. **隐私**：图片元数据可能含GPS等敏感信息，分析后不外传