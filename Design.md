# 拆分-评估-调整循环设计文档
## 1. 循环设计
闭环流水线：
1. 初次拆分
2. QA 评估：对比原始需求R和拆分结果J，输出错误列表E
3. 判定是否存在拆分错误
4. 修复拆分结果
5. 循环限制：最多允许重试N次
## 2. 接口设计
a. decomposer_and_fix
输入：string req_text, string prompt, dict previous_json/Optional, list qa_feedback/Optional
输出：dict parsed_json
b. evaluator
输入：string req_text, dict parsed_json, string evaluator_prompt
输出：dict eval_result
## 3. 核心逻辑
```python
MAX_FIX_RETRIES = 2  # 生产环境中单条需求最多允许修复的次数

def decomposer_and_fix(req_text, system_prompt, previous_json=None, qa_feedback=None):
     # 场景 A：初次拆分（没有历史包袱）
    if previous_json is None:
    # 场景 B：修复模式（自我反思）
    else:

def evaluate_split(req_text, parsed_json, eval_system_prompt):
    # 调用裁判模型

def process_requirement_pipeline(req_text, split_prompt, eval_prompt):
    current_json = split_and_fix_requirement(req_text, split_prompt)
    for attempt in range(MAX_FIX_RETRIES + 1):
        # 退出条件：如果没有报错，或者得分极高
        # 如果还有重试机会，则进行自我修复
```
分析：当触发修复模式时，将 “原文 + 错题本 + 批改意见” 三者同时塞给大模型。大模型看到自己之前的错误输出和 QA 的报错，会极大地激发其逻辑修正能力，第二次生成的 JSON 通常会完美填补漏洞。
为什么设置 MAX_FIX_RETRIES = 2？
答：在工程实践中，大模型的自我修复具有“边际效用递减”特性。