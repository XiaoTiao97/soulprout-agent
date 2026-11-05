import os
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# -------------------------- 配置项，支持从 agent/.env 读取 --------------------------
MONGO_HOST = (os.getenv("MONGO_HOST") or os.getenv("DOCKER_SERVER_HOST") or "localhost").strip()
MONGO_PORT = int((os.getenv("MONGO_PORT") or "27017").strip())
MONGO_USER = (os.getenv("MONGO_USER") or "").strip()
MONGO_PASSWORD = (os.getenv("MONGO_PASSWORD") or "").strip()
MONGO_AUTH_SOURCE = (os.getenv("MONGO_AUTH_SOURCE") or "admin").strip()
DB_NAME = (os.getenv("MONGO_DATABASE") or "soulprout").strip()
USER_COLLECTION = "user_info"  # 用户信息集合名
CONV_COLLECTION = "conversations"  # 会话集合名


def _build_mongo_client() -> MongoClient:
    if MONGO_USER and MONGO_PASSWORD:
        u = quote_plus(MONGO_USER)
        p = quote_plus(MONGO_PASSWORD)
        uri = f"mongodb://{u}:{p}@{MONGO_HOST}:{MONGO_PORT}/?authSource={quote_plus(MONGO_AUTH_SOURCE)}"
        return MongoClient(uri)
    return MongoClient(host=MONGO_HOST, port=MONGO_PORT)


# ---------------------------------------------------------------------------

def get_user_stats():
    # 连接MongoDB
    client = _build_mongo_client()
    db = client[DB_NAME]

    # 1. 获取总用户数
    total_users = db[USER_COLLECTION].distinct("user_id")
    total_user_count = len(total_users)

    # 计算时间节点（UTC时间，和updated_at格式匹配）
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    week_active_users = []
    month_active_count = 0
    user_conv_count = {}  # 存近一周活跃用户的会话数量

    # 2. 遍历所有用户统计数据
    for user_id in total_users:
        # 查询用户最新的一条会话记录
        latest_conv = db[CONV_COLLECTION].find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1)]
        )

        if not latest_conv:
            continue

        # 统计近一个月活跃
        if latest_conv["updated_at"] >= thirty_days_ago:
            month_active_count += 1

        # 统计近一周活跃 + 近一周会话数量
        if latest_conv["updated_at"] >= seven_days_ago:
            week_active_users.append(user_id)
            # 统计该用户近一周的会话总数
            conv_count = db[CONV_COLLECTION].count_documents({
                "user_id": user_id,
                "updated_at": {"$gte": seven_days_ago}
            })
            user_conv_count[user_id] = conv_count

    # 关闭连接
    client.close()

    return {
        "total_user_count": total_user_count,
        "month_active_count": month_active_count,
        "week_active_count": len(week_active_users),
        "week_active_user_ids": week_active_users,
        "week_user_conv_count": user_conv_count
    }


if __name__ == "__main__":
    # 没装pymongo的话先运行 pip install pymongo
    stats = get_user_stats()
    print(f"总用户数：{stats['total_user_count']}人")
    print(f"近一个月使用人数：{stats['month_active_count']}人")
    print(f"近一周使用人数：{stats['week_active_count']}人")
    print("\n近一周活跃用户详情：")
    for user_id in stats['week_active_user_ids']:
        print(f"用户ID：{user_id}，近一周会话数：{stats['week_user_conv_count'][user_id]}条")
