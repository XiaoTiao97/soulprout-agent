from fastapi import APIRouter, HTTPException, Request, Form
from agent.services.auth import get_current_user
from agent.database.crud.conversation import get_conversations_by_user, delete_conversation_by_conv, get_conversation_by_id, update_conversation_by_conv_for_abstract, delete_sub_agent_conversation_by_conv
from agent.database.crud.message import delete_message_by_conv_id, delete_local_files, delete_sub_agent_message_by_conv_id
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/conversations")
async def get_conversations(request: Request):
    token = request.cookies.get("token")
    if token:
        user = await get_current_user(token)
        conversations = await get_conversations_by_user(user.user_id)
        return conversations
    else:
        return JSONResponse(status_code=404, content={
            "success": False,
            "message": "token失效",
            "code": 404
        })

@router.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    try:
        conversation = await get_conversation_by_id(conversation_id=conversation_id)
        return conversation
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"获取对话失败，失败原因：{e}",
            "code": 1004
        })


@router.delete("/conversations/{conversation_id}")
async def delete_conversations(conversation_id: str):
    try:
        # 建议 services 层加一层 user_id 检查，防止删除别人对话
        await delete_conversation_by_conv(conversation_id)
        await delete_sub_agent_conversation_by_conv(conversation_id)
        await delete_message_by_conv_id(conversation_id)
        await delete_sub_agent_message_by_conv_id(conversation_id)
        await delete_local_files(conversation_id)
        return JSONResponse(status_code=200, content={
            "success": True,
            "message": "已删除对话"
        })
    except Exception as e:
        return JSONResponse(status_code=200, content={
            "success": False,
            "message": f"删除对话失败，失败原因: {e}",
            "code": 1004
        })

@router.post("/conversation/{conversation_id}")
async def update_conversation_abstract(conversation_id: str, abstract: str = Form(...)):
    abstract = abstract.strip()
    if not abstract:
        raise HTTPException(status_code=400, detail="abstract 不能为空")
    try:
        await update_conversation_by_conv_for_abstract(conversation_id, abstract)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "已更新abstract",
                "conversation_id": conversation_id,
                "abstract": abstract,
            },
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"更新abstract失败，失败原因: {e}",
                "code": 1004,
            },
        )