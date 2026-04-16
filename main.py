import json
import os
from openai import OpenAI


# 1. 配置 API 客户端 
API_KEY = "81a850f41bea4d1c93a583937e818307.CMgqnfJkjboW6Sva" 
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/" 
MODEL_NAME = "glm-4-plus"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# 2. 定义初始版本的提示词 
SYSTEM_PROMPT_V1 = """
[角色设定]
你是一个极度严谨的、具有“代码编译器”思维的软件需求分析师。你的任务是将长文本需求完全解构，并且保证信息 100% 守恒。

[拆分规则（最高指令）]
1. 极限原子化的边界界定（严防过度拆分与欠拆分）：
   - 必须拆分（不同动作）：遇到“创建、删除、修改、查询”等并列的不同操作，必须一对一拆分为绝对独立的子需求！绝不允许漏掉任何一个（特别是“删除”）。
   - 严禁拆分（同类数据对象）：如果原文是同一个动作处理多个对象（如：“实时采集温度、压力、电流、功率”），**严禁将它们拆散为多个需求**！必须作为一个整体需求，并在描述和 AC 中穷举所有数据对象。
   - 业务流切断：具有先后顺序的连续操作（如：调整灵敏度 -> 选择公差范围），必须斩断为独立子需求。

2. 强制异常分支捕获：
   - 扫描原文，只要出现“无...时提示”、“...否则报错”、“失败时输出”、“若不存在则...”等异常处理，必须将其写为一条独立的异常 AC。

3. 绝对穷举提取（严防长列表截断与泛化）：
   - 数量词核对：原文中的数量词（如“20类数据”、“64种模式”），你必须“逐个点名”，总数必须完全吻合！
   - 禁用概括词：绝对不允许将原文中的“绝对层级路径”、“相对层级路径”等硬核技术词汇概括为“符合语法”，必须 100% 照抄原词！

4. 彻底隔离全局与局部（严防全局污染）：
   - 放全局 (`global_info`) 的：仅限【目标用户】、【贯穿整个系统的平台/OS/网络依赖】、【所有接口共用的安全规则】。
   - 留局部 (留在子需求中) 的：任何带有特定前缀的时间限制（如：阶段1自检≤10秒、偏置图计算≤10秒）、特定接口的错误处理逻辑（如：C++ API的默认参数）、特定的语法要求。**只要它只影响局部功能，死也不能放进 global_info！**

5. 彻底的无菌化客观输出（严防模糊词汇）：
   - 禁用词库：绝对禁止在 AC 中使用“流畅”、“及时”、“正常”、“成功”、“大致一致”、“尝试”、“当系统启动时（过于笼统）”等无法测试的废话！

[输出格式]
必须以严格的 JSON 格式输出。严格遵守以下数据结构和注释警告：

{
  "global_info": {
    "target_users_and_value": "[提取真实存在的用户/价值，原文若无则填 null]",
    "technical_and_env_constraints": [
      "[仅限贯穿全系统的OS/网络/大盘依赖，绝不能包含特定功能的秒数、时间或报错逻辑！原文若无填 []]"
    ]
  },
  "sub_requirements": [
    {
      "id": "REQ-1",
      "title": "[单一动宾短语，如：调整诊断灵敏度]",
      "description": "[必须穷举包含该动作相关的所有数值、枚举值、专用名词（如绝对层级路径）]",
      "acceptance_criteria": [
        "(严重警告：此处数组长度绝对不可超过 4！若发现 AC 数量即将超过 4，说明你合并了连续流程，必须立刻拆解为新的 REQ！)",
        "AC1 (正常): 当【明确前置条件，如：用户输入正确/接收到CCD图像】时，执行【动作】，系统应【明确可测结果，照抄原文极值，如：优化至2.5角秒/包含唯一数字证书】",
        "AC2 (异常): 当【明确失败条件，如：未找到文件/绑定名称不符】时，系统应【明确异常反馈，如：提示'file not found'/绑定失败】"
      ]
    }
  ]
}
"""

# 3. 核心处理函数
def split_requirement(req_text, system_prompt):
    """调用大模型拆分单条需求"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"请按要求拆分以下原始需求：\n\n{req_text}"}
    ]
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0, # 低温度保证输出格式的稳定性和逻辑的严谨性
            response_format={"type": "json_object"} # 强制要求模型输出 JSON 格式
        )
        
        # 提取模型的文本回复
        result_content = response.choices[0].message.content
        
        # 将文本解析为 Python 字典
        return json.loads(result_content)
        
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败，模型输出格式不规范: {e}")
        return {"error": "JSON解析失败", "raw_output": result_content}
    except Exception as e:
        print(f"API 调用失败: {e}")
        return None

# 4. 主流程：读取、遍历、处理、保存
def main():
    input_file = "bad_results.json"   # 你的原始数据文件
    output_file = "split_4.json"
    
    # 1. 读取原始数据
    if not os.path.exists(input_file):
        print(f"找不到文件 {input_file}")
        return
        
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"成功加载 {len(data)} 条需求，开始处理...")
    
    final_results = []
    
    # 2. 遍历处理 
    for item in data[:20]:
        row_id = item.get("row")
        req_text = item.get("req")
        
        print(f"\n正在处理 Row: {row_id}...")
        
        # 调用大模型
        split_result = split_requirement(req_text, SYSTEM_PROMPT_V1)
        
        if split_result:
            print(f"Row {row_id} 拆分成功！提取了 {len(split_result.get('sub_requirements', []))} 个子需求。")
            final_results.append({
                "row": row_id,
                "original_req": req_text,
                "parsed_result": split_result
            })
            
    # 3. 写入结果文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
        
    print(f"\n处理完毕！结果已保存至 {output_file}")

if __name__ == "__main__":
    main()