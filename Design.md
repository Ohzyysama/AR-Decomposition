# 拆分-评估-调整循环设计文档
## 1. 循环设计
闭环流水线：拆分 -> 评估 -> 调整prompt -> 再次拆分 -> 评估...
流水线中的三个角色：Generator, Evaluator, Optimizer
## 2. 接口设计
a. decomposer
输入：string req_text, string prompt
输出：dict parsed_json
b. evaluator
输入：string req_text, dict parsed_json, string evaluator_prompt
输出：dict eval_result
c. optimizer
输入：string current_prompt, list eval_feedback_list
输出：string new_prompt
## 3. 核心逻辑
```python
def prompt_evaluation_loop(dataset, initial_prompt, evaluator_prompt, max_epochs=3):
    current_prompt = initial_prompt

    for epoch in range(max_epochs):
        for row in dataset:
            #用当前prompt拆分
            #裁判打分
        #判断是否达标
        #如未达标则进行优化
```
分析：设置最多优化3次，在每次优化的循环中，对多条需求进行拆分和评估(只用一两条需求容易发生过拟合)，若达到标准(评估结果中错误数为0)，则跳出循环，否则进行优化后再次重复该流程。