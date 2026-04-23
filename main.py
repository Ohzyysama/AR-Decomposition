import json
import os
import textwrap
from openai import OpenAI

# 1. 配置 API 客户端 
API_KEY = "81a850f41bea4d1c93a583937e818307.CMgqnfJkjboW6Sva" 
BASE_URL = "https://open.bigmodel.cn/api/paas/v4/" 
MODEL_NAME = "glm-4-plus"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# ==========================================
# 2. 从原异步代码中提取的提示词与模板常量
# ==========================================

REQ_FORMAT_CONTENT = textwrap.dedent("""
    【需求价值】
    该需求旨在解决何种核心问题，或为用户及业务带来何种收益。
    【需求场景】
    该需求的适用业务场景与具体触发条件。
    【需求描述】
    该需求需实现功能的详细说明，包括主要流程与关键交互。
    【目标用户】
    该需求的明确使用人群，例如某类终端用户或系统角色。
    【限制约束】
    实现该需求需满足的约束条件，如用户前置操作、技术或业务限制等。
    【外部依赖】
    该需求所依赖的外部系统、组件或服务。
    【性能指标】
    该需求的性能要求，例如响应时间、并发能力等指标，需明确对比基线或提升目标。
    【ROM&RAM】
    该需求对设备存储（ROM）与内存（RAM）的占用要求，需明确对比基线或优化目标。
    【验收标准】
    该需求通过验收的判定条件与依据，例如功能完整性、性能达成度等维度。
    【验收设备】
    验收该需求所需的设备类型与测试环境，如特定型号手机、操作系统版本等。
    【使用产品差异分析】
    该需求在不同设备或平台上的使用行为差异；如无差异，需明确说明。
    【2D生态】
    该需求对面向开发者的软件生态建设可能产生的影响。
""")

# 【重构说明】：删除了冗余的 global_info 和 acceptance_criteria。
# 强制要求大模型把所有要素融进 description 的 12 个标签中。
JSON_SCHEMA_DEFINITION = textwrap.dedent("""\
{
  "type": "object",
  "properties": {
    "sub_requirements": {
      "type": "array",
      "description": "分解后的微型需求书列表",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string", "description": "编号，如'REQ-01'" },
          "title": { "type": "string", "description": "单一动宾短语标题" },
          "description": { 
            "type": "string", 
            "description": "该子需求的完整微型需求书。必须包含全部 12 个【标签】。请将全局约束、目标用户、验收标准等归纳进对应的标签内。" 
          }
        },
        "required":["id", "title", "description"]
      }
    }
  },
  "required":["sub_requirements"]
}
""")

SYSTEM_PROMPT_V1 = textwrap.dedent(f"""
    [角色设定]
    你是一个极度严谨的软件需求架构师。你的任务是将长文本需求，解构为一组颗粒度极细、且自带完整上下文的“微型需求书（User Stories）”。

    [输出格式铁律（最高优先级）]
    在生成每个子需求的 `description` 字段时，**必须以文本形式，按顺序完整包含以下《需求格式定义》中的全部 12 个【标签】**！
    - 全局信息归位：请将原文中的全局目标用户、底层技术限制、外部组件依赖，直接归纳进每一个子需求的【目标用户】、【限制约束】、【外部依赖】标签中。
    - AC归位：请将验收标准的 Given-When-Then 断言，直接写进【验收标准】标签中。

    --- 需求格式定义（description 必须包含的结构） ---
    {REQ_FORMAT_CONTENT}
    --- 需求格式定义结束 ---

    请严格遵循以下 JSON Schema 构造输出：
    ```json
    {JSON_SCHEMA_DEFINITION}
    ```
""")

DECOMPOSITION_RULES =[
    "【动作极限切分】遇到'创建、删除、修改'等并列操作，必须一对一拆分为绝对独立的子需求！具有先后顺序的业务流也必须斩断为独立子需求。",
    "【标签精准投递】原文提到的'Windows/Linux等操作系统'、'TCP/IP协议'必须填入【限制约束】或【外部依赖】；'24x7高可用'等必须填入【性能指标】。决不允许遗漏！",
    "【AC规范与限制】在填写【验收标准】标签时，最多列出 4 条 Given-When-Then 格式的验证点（必须包含异常失败分支）。绝对禁止使用'流畅'、'正常'等废话，必须包含具体的数值、报错提示语（如：提示'file not found'）。",
    "【防截断指令（防 Token 溢出）】为了防止输出过长被截断，如果多个子需求的【需求价值】、【目标用户】、【2D生态】等标签内容完全一样，请极简概括（如填写：'同系统全局目标'或'无'），把字数额度留给【需求描述】和【验收标准】！",
    "【极值与名词的强绑定】提取信息时，必须连带其主语、量词一并抄入！必须写'计数率<2cps'（不能只写'<2cps'）；必须写'记录在EEPROM'。"
]

FORMAT_INSTRUCTION = None  # 额外要求，可填入字符串


# ==========================================
# 3. 核心处理函数
# ==========================================

def build_user_prompt(original_requirement: str, rules: list, specific_instruction: str = None) -> str:
    """提取自原代码的 User Prompt 组装逻辑"""
    prompt_parts = []

    prompt_parts.append("\n=== 分解规则 ===")
    for i, rule in enumerate(rules, 1):
        prompt_parts.append(f"{i}. {rule}")

    prompt_parts.append("\n=== 原始需求 ===")
    prompt_parts.append(original_requirement)

    if specific_instruction:
        prompt_parts.append("\n=== 额外要求 ===")
        prompt_parts.append(specific_instruction)

    return '\n'.join(prompt_parts)


def split_requirement(req_text, system_prompt, rules, instruction):
    """调用大模型拆分单条需求"""
    
    # 使用组装函数构建 user_prompt
    user_prompt = build_user_prompt(req_text, rules, instruction)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0, # 低温度保证输出格式的稳定性和逻辑的严谨性
            max_tokens=8192,
            response_format={"type": "json_object"} # 强制要求模型输出 JSON 对象
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

# ==========================================
# 4. 主流程：读取、遍历、处理、保存
# ==========================================

def main():
    input_file = "bad_results.json"   # 你的原始数据文件
    output_file = "split_normal.json"
    
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
        
        # 传入规则和指令调用大模型
        split_result = split_requirement(
            req_text=req_text, 
            system_prompt=SYSTEM_PROMPT_V1,
            rules=DECOMPOSITION_RULES,
            instruction=FORMAT_INSTRUCTION
        )
        
        if split_result:
            # 因为 Schema 被调整为了包含 sub_requirements，这里做相应的计数提取
            extracted_items = split_result.get('sub_requirements', [])
            print(f"Row {row_id} 拆分成功！提取了 {len(extracted_items)} 个子需求。")
            
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