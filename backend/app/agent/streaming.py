from langchain_core.messages import AIMessage, BaseMessage


def assistant_text(message: BaseMessage) -> str:
    """Extract public assistant text, never tool results, arguments, or reasoning blocks.

    Legacy LangGraph messages streams include completed ToolMessages as well as model
    chunks. Both may contain strings or text blocks; content shape alone is not a role.
    """
    if not isinstance(message, AIMessage):
        return ""
    if isinstance(message.content, str):
        return message.content
    return "".join(
        block["text"]
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    )
