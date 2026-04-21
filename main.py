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

# 【修改点1】：在 Schema 中强制要求 description 包含完整结构标签
JSON_SCHEMA_DEFINITION = textwrap.dedent("""\
{
  "type": "object",
  "properties": {
    "global_info": {
      "type": "object",
      "description": "提取的全局信息，用于隔离系统级约束",
      "properties": {
        "target_users_and_value": { "type": "string", "description": "系统整体目标用户与业务价值" },
        "technical_and_env_constraints": {
          "type": "array",
          "items": { "type": "string" },
          "description": "贯穿全系统的底层OS、全局通用协议等"
        }
      },
      "required":["target_users_and_value", "technical_and_env_constraints"]
    },
    "sub_requirements": {
      "type": "array",
      "description": "分解后的原子化子需求列表",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string", "description": "子需求编号，如'REQ-01'" },
          "title": { "type": "string", "description": "单一动宾短语标题" },
          "description": { 
            "type": "string", 
            "description": "【核心要求】该子需求的完整结构化文本。必须包含《需求格式定义》中的全部 12 个【标签】！并根据该子需求的具体内容进行填充。" 
          },
          "acceptance_criteria": {
            "type": "array",
            "items": { "type": "string" },
            "description": "验收标准，采用 Given-When-Then 格式",
            "maxItems": 4
          }
        },
        "required":["id", "title", "description", "acceptance_criteria"]
      }
    }
  },
  "required":["global_info", "sub_requirements"]
}
""")

# 【修改点2】：撤销禁令，明确要求大模型将 12 个标签写进 description 中
SYSTEM_PROMPT_V1 = textwrap.dedent(f"""[角色设定]
    你是一个极度严谨的、具有“代码编译器”思维的软件需求架构师。你的任务是将长文本需求解构为 JSON。

    [格式完整性要求（最高优先级）]
    你必须为每一个拆分出来的子需求(sub_requirements)生成**完整的需求结构**！
    在生成每个子需求的 `description` 字段时，**必须以文本形式，按顺序完整包含以下《需求格式定义》中的所有 12 个【标签】**！
    如果该子需求在某个标签下（如【ROM&RAM】或【2D生态】）没有特定信息，请填写“无”或“同全局配置”，但**绝对不允许省略任何一个【标签】**！

    --- 需求格式定义（子需求 description 必须包含的结构） ---
    {REQ_FORMAT_CONTENT}
    --- 需求格式定义结束 ---

    [输出格式铁律]
    你必须严格遵循以下 JSON Schema 来构造你的输出。绝对不能丢失 `global_info` 和 `acceptance_criteria` 字段！
    
    --- JSON Schema定义 ---
    ```json
    {JSON_SCHEMA_DEFINITION}
    ```
    --- JSON Schema定义结束 ---
""")

# 【修改点3】：移除之前关于全局污染的强力限制，保留动作拆解规则
DECOMPOSITION_RULES =[
    "【结构化填充原则】在拆分出单一动作后，请结合原文的上下文，将该动作相关的目标用户、使用场景、限制约束等，精准地填入该子需求 description 对应的【标签】中。",
    "【极值与名词的强绑定】提取极值或状态时，必须连带其主语、量词和存储位置一并抄入！不能只写'<2cps'，必须写'计数率<2cps'；不能只写'记录在BIT_DATA'，必须写'记录在EEPROM的BIT_DATA'。",
    "【开关动作的防坑表述】对于'启用/禁用'某功能，绝不能写成'启用并压缩'（会被误判为两个动作）。必须表述为单一动作，如：'开启数据压缩功能' 或 '禁用数据压缩功能'。",
    "【同动词/异宾语及CRUD极限拆分】即使动作相同，只要目标/范围不同（如浏览『当前』与『历史』），必须强制拆分！针对新增、删除、修改，必须一对一拆分！绝不允许合并！",
    "【长列表绝对对齐】原文提到20类数据，你在拆分结果中必须原原本本覆盖20类数据！遇到长列表，严防截断！",
    "【AC无菌化客观输出】单条子需求的AC数量不得超过4条。遇到“无..时提示”、“失败则..”，必须独立写为异常AC。绝对禁止在AC中使用“流畅”、“及时”、“正常”、“成功”等废话！",
    "【防止信息膨胀截断】在填充每个子需求的 12 个标签时，对于【需求价值】、【需求场景】、【目标用户】、【外部依赖】等与全局完全一致的内容，**绝对禁止长篇大论地重复抄写**！请直接简写为“同全局配置”或极简概括（限10字以内）。你必须把有限的输出额度留给【需求描述】和【验收标准】！"
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
    output_file = "split_normal_8.json"
    
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