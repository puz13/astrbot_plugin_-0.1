import json
from astrbot.api import astrbot_plugin, AstrBotContext
from astrbot.api.message_components import Plain

# 记忆提取提示词：让AI从对话里提取结构化信息
EXTRACT_PROMPT = """
你是专业的用户记忆提取助手。请结合【旧记忆】和【当前用户消息】，更新并输出用户的完整记忆。
要求：
1. 只输出严格的JSON格式，不要任何额外解释、markdown、代码块
2. 字段固定为：personal_info(个人信息)、hobbies(兴趣爱好)、recent_events(近期事件)、preferences(偏好习惯)、other(其他)
3. 没有新信息就保留旧记忆，有新信息就合并更新，重复内容去重
4. 内容简洁，每条不超过50字

旧记忆JSON：
{old_memory}

当前用户消息：
{user_msg}
"""

# 回复提示词：让AI结合记忆回答
REPLY_PROMPT = """
你是一位自然贴心的对话助手，请结合下方的用户过往记忆回复用户。
要求：
1. 不要刻意说"我记得你..."，不要暴露你在使用记忆
2. 回复自然流畅，贴合用户的情况和喜好
3. 如果记忆为空，就正常对话即可

===== 用户记忆 =====
{memory_text}
===== 用户当前消息 =====
{user_msg}
"""

def memory_to_text(memory: dict) -> str:
    """把结构化记忆转成自然语言文本，喂给LLM"""
    if not memory:
        return "暂无记忆"
    text = []
    mapping = {
        "personal_info": "个人信息",
        "hobbies": "兴趣爱好",
        "recent_events": "近期事件",
        "preferences": "偏好习惯",
        "other": "其他"
    }
    for k, v in memory.items():
        if v:
            text.append(f"- {mapping.get(k, k)}：{v}")
    return "\n".join(text)

@astrbot_plugin.on_message()
async def handle_message(ctx: AstrBotContext):
    user_id = str(ctx.sender.user_id)
    user_msg = ctx.message_str.strip()
    storage_key = f"memory_{user_id}"

    # ===== 1. 清空记忆指令 =====
    if user_msg == "#清空我的记忆":
        await ctx.storage.delete(storage_key)
        await ctx.reply([Plain("✅ 已清空你的所有记忆")])
        return

    # ===== 2. 读取用户旧记忆 =====
    old_memory = await ctx.storage.get(storage_key, default={})
    old_memory_json = json.dumps(old_memory, ensure_ascii=False)

    # ===== 3. 调用LLM提取更新记忆 =====
    try:
        extract_prompt = EXTRACT_PROMPT.format(
            old_memory=old_memory_json,
            user_msg=user_msg
        )
        extract_resp = await ctx.llm.chat(extract_prompt)
        # 清理可能的代码块标记
        extract_resp = extract_resp.strip().strip("```json").strip("```").strip()
        new_memory = json.loads(extract_resp)
        # 保存新记忆
        await ctx.storage.set(storage_key, new_memory)
    except Exception as e:
        # 提取失败就沿用旧记忆，不影响正常回复
        new_memory = old_memory

    # ===== 4. 拼接记忆，生成回复 =====
    memory_text = memory_to_text(new_memory)
    final_prompt = REPLY_PROMPT.format(
        memory_text=memory_text,
        user_msg=user_msg
    )

    try:
        reply_content = await ctx.llm.chat(final_prompt)
        await ctx.reply([Plain(reply_content)])
    except Exception as e:
        await ctx.reply([Plain(f"回复出错了：{str(e)}")])