#!/usr/bin/env python3
import re

"""Curated registry of current major Chinese NEN guidelines/consensus.
Entries verified against publisher/journal sources (2026-09). Editor-maintained:
update this list when new editions are released.
"""

# 每条：title / org / source / year / url / scope（覆盖范围）/ note（要点）
GUIDELINES = [
    {"title": "中国抗癌协会神经内分泌肿瘤诊治指南（2025年版）",
     "org": "中国抗癌协会（CACA）神经内分泌肿瘤专业委员会",
     "source": "中国癌症杂志 2025;35(1):85-142",
     "year": 2025,
     "url": "https://www.china-oncology.com/",
     "doi": "10.19401/j.cnki.1007-3639.2025.01.010",
     "scope": "泛 NEN 全谱",
     "note": "现行最全面的整合版中国 NEN 指南：在 2022 版基础上更新，并扩充至垂体神经内分泌瘤（PitNET）、甲状腺髓样癌（MTC）、嗜铬细胞瘤/副神经节瘤（PPGL）与 Merkel 细胞癌；已在 PREPARE 平台注册（PREPARE-2024CN1158）；分期采用第 9 版 AJCC（GEP-NET 与胸部 NEN 已更新）。"},
    {"title": "中国肿瘤整合诊治指南（CACA）神经内分泌肿瘤 V2.0（2025）",
     "org": "中国抗癌协会神经内分泌肿瘤专业委员会",
     "source": "CACA 指南平台（2025-01-10 发布）",
     "year": 2025,
     "url": "https://cacaguidelines.cacakp.com/pdflist?guide_id=1017",
     "doi": None,
     "scope": "泛 NEN 全谱",
     "note": "CACA 整合诊治指南 NEN 分册 2025 版（V2.0），另有英文版 V1.0（2024-08-28）；与上条同源，按整合诊治（防-筛-诊-治-康）体例编排。"},
    {"title": "中国胃肠胰神经内分泌肿瘤专家共识（2022年版）",
     "org": "中国临床肿瘤学会（CSCO）神经内分泌肿瘤专家委员会",
     "source": "中华肿瘤杂志 2022;44(12):1305-1329",
     "year": 2022,
     "url": "https://pubmed.ncbi.nlm.nih.gov/",
     "doi": None,
     "scope": "GEP-NEN",
     "note": "CSCO 系列共识（2013/2016/2022）最新版：分胰腺 NEN 与胃肠道 NEN 两部分，覆盖流行病学、生化与影像检查（含 SSTR PET/18F-FDG PET-CT）、病理（2019 WHO 分级；menin/p27、SSTR2 等标志物鉴别 NET G3 与 NEC）、药物治疗与随访。"},
    {"title": "中国胰腺神经内分泌肿瘤诊疗指南（2020）",
     "org": "中华医学会外科学分会胰腺外科学组（中国胰腺病协会/多学科专家委员会）",
     "source": "协和医学杂志 2021;12(4):460-480",
     "year": 2020,
     "url": "https://xhyxzz.pumch.cn/article/doi/10.12290/xhyxzz.2021-0481",
     "doi": "10.12290/xhyxzz.2021-0481",
     "scope": "pNEN",
     "note": "胰腺 NEN 专科诊疗指南：外科牵头，覆盖多学科（内分泌、影像、病理、核医学）诊疗建议；替代 2014 版《胰腺神经内分泌肿瘤治疗指南》。"},
    {"title": "中国胃肠胰神经内分泌肿瘤病理诊断共识（2020版）",
     "org": "中华医学会病理学分会消化疾病学组 / 中国胃肠胰NEN病理诊断共识专家组",
     "source": "中华病理学杂志 2021;50(01)",
     "year": 2020,
     "url": "https://pubmed.ncbi.nlm.nih.gov/33396981/",
     "doi": None,
     "scope": "GEP-NEN 病理",
     "note": "病理诊断核心共识（2011/2013/2020 系列）：按第 5 版 WHO 明确分类分级分期，重点阐述 NET G3 与 NEC 的鉴别（TP53/RB 失活 vs ATRX/DAXX 缺失）、免疫组化必做/选做项目与 MiNEN 处理。PMID 33396981。"},
    {"title": "胃肠胰神经内分泌肿瘤诊治专家共识（2020·广州）",
     "org": "中华医学会消化病学分会胃肠激素与神经内分泌肿瘤学组",
     "source": "中华消化杂志",
     "year": 2020,
     "url": "https://www.shsma.org.cn/branch/newcontent/44/8082",
     "doi": None,
     "scope": "GEP-NEN 内科/消化",
     "note": "消化内科视角（替代 2014 版《内科诊治若干建议》）：涵盖内镜表现与分型（1/2/3 型胃 NET）、EUS 特征、2019 WHO 分级、内外科与核医学治疗；指出中国 GEP-NEN 好发部位依次为胰腺、直肠和胃（与欧美以小肠为主不同）。"},
    {"title": "胃肠胰神经内分泌肿瘤影像学诊断专家共识（2024年）",
     "org": "中华医学会消化病学分会消化影像协作组",
     "source": "中华消化病与影像杂志(电子版) 2024;14(02):97-106",
     "year": 2024,
     "url": "https://zhxhbyyxzz.cma-cmc.com.cn/CN/10.3877/cma.j.issn.2095-2015.2024.02.001",
     "doi": "10.3877/cma.j.issn.2095-2015.2024.02.001",
     "scope": "GEP-NEN 影像",
     "note": "影像学专科共识：比较 CT/MRI/核医学（SRI）/超声内镜/胃肠内镜的优劣与适用场景，给出诊断-分期-随访的检查路径建议。"},
]

# 检索层自动识别中国指南/共识文献的正则（处理层使用）
GUIDELINE_TITLE = re.compile(r"consensus|guideline|expert (agreement|recommendation|consensus)|专家共识|指南|共识", re.I)
GUIDELINE_CN = re.compile(r"China|Chinese|中华|中国", re.I)
