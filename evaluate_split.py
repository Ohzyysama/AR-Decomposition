import json
import os
from openai import OpenAI

# 1. 配置 API 客户端
API_KEY = "81a850f41bea4d1c93a583937e818307.CMgqnfJkjboW6Sva"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
MODEL_NAME = "glm-4-plus"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 2. 定义评估者的系统提示词
EVALUATOR_SYSTEM_PROMPT = """
[角色设定]
你是一个冷酷、客观的自动化代码审计系统。你的任务是严格比对【原始需求】与【拆分后的JSON结果】，寻找拆分过程中的信息丢失和规则破坏。

[审计算法]
1. 实体丢失（扣5分）：检查原始需求中的数字、专有名词、限制条件，是否在拆分JSON中遗漏。
2. AC超载（扣10分）：检查JSON中是否有任何 `acceptance_criteria` 的列表长度大于 4。
3. 动词重叠（扣15分）：检查同一个子需求内是否塞入了多个独立动作。
4. 全局污染（扣10分）：检查子需求内是否错误地包含了环境、平台、语言等本该放在全局的信息。
5. AC模糊（扣5分）：检查AC中是否缺乏明确的前置条件和预期结果。

[最高指令]
1. 你的分析和报错必须 **100% 基于用户输入的真实文本**！
2. **严禁瞎编乱造！** 如果 JSON 拆分得完全符合要求，没有遗漏和违规，你必须输出 100分 且 error_count 为 0！

[输出格式（严格遵守以下JSON结构，不要输出 Markdown）]
{
  "reasoning_process": "步骤1：提取原文实体，比对发现...。步骤2：检查AC长度，最大长度为... 步骤3：检查动词...",
  "score": <根据扣分规则计算的最终得分，如果没有错就是100>, 
  "error_count": <真实发现的错误总数，如果没有错就是0>,
  "violation_details": [
    {
      "rule": "<填入上面5个审计算法之一的名称>",
      "sub_req_id": "<填入存在错误的真实子需求ID>",
      "description": "<详细说明原文写了什么，而JSON中哪里做错了。必须基于真实情况>"
    }
  ],
  "prompt_improvement_suggestion": "<基于找出的真实错误给出优化建议，没有错就填无>"
}
"""

# 3. 核心评估函数
def evaluate_split_result(original_req, parsed_json):
    
    # 将拆分结果转回字符串以便给大模型阅读
    parsed_str = json.dumps(parsed_json, ensure_ascii=False, indent=2)
    
    user_content = f"""
    请评估以下需求拆分结果：
    
    【原始需求】
    {original_req}
    
    【拆分后的JSON结果】
    {parsed_str}
    
    请严格按照规则输出评估JSON。
    """

    messages = [
        {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.1, # 保持低温度，客观评分
            response_format={"type": "json_object"} 
        )
        result_content = response.choices[0].message.content
        return json.loads(result_content)
        
    except Exception as e:
        print(f"评估 API 调用或解析失败: {e}")
        return None

# 4. 主流程
def main():
    input_file = "split_normal_7.json"   # 上一个程序生成的拆分结果
    output_file = "evaluation_normal_7.json"
    
    if not os.path.exists(input_file):
        print(f"找不到文件 {input_file}，请先运行拆分程序。")
        return
        
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"成功加载 {len(data)} 条拆分结果，开始阅卷评估...")
    
    evaluation_results = []
    total_score = 0
    total_errors = 0
    
    for item in data:
        row_id = item.get("row")
        original_req = item.get("original_req")
        parsed_result = item.get("parsed_result")
        
        print(f"\n正在评估 Row: {row_id}...")
        
        eval_result = evaluate_split_result(original_req, parsed_result)
        
        if eval_result:
            score = eval_result.get('score', 0)
            err_count = eval_result.get('error_count', 0)
            
            print(f"Row {row_id} 评估完成！得分: {score}，发现错误数: {err_count}")
            if err_count > 0:
                for v in eval_result.get('violation_details', []):
                    print(f"扣分项: [{v.get('rule')}] {v.get('description')}")
            
            total_score += score
            total_errors += err_count
            
            evaluation_results.append({
                "row": row_id,
                "score": score,
                "error_count": err_count,
                "violation_details": eval_result.get('violation_details', []),
                "prompt_improvement_suggestion": eval_result.get('prompt_improvement_suggestion', "")
            })
            
    # 写入评估结果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(evaluation_results, f, ensure_ascii=False, indent=2)
        
    # 打印全局统计，指导下一步的 Prompt 优化
    avg_score = total_score / len(data) if data else 0
    print("\n" + "="*50)
    print("评估总结（用于优化你的拆分提示词）")
    print("="*50)
    print(f"总评估数: {len(data)} 条")
    print(f"平均得分: {avg_score:.2f} / 100")
    print(f"总计错误: {total_errors} 处")
    print(f"详细报告已保存至: {output_file}")
    print("\n下一步：打开 evaluation_results.json，查看 'prompt_improvement_suggestion' 字段，把这些建议补充到你第一个程序的 SYSTEM_PROMPT 中！")

if __name__ == "__main__":
    main()