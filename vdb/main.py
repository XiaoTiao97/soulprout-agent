import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

from vdb.core.config import VDBConfig
from vdb.services.milvus import MilvusService
from vdb.api.routers import router as api_router

config = VDBConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：建立 Milvus 连接，挂载到 app.state
    milvus_svc = MilvusService(config)
    await milvus_svc.connect()
    app.state.milvus = milvus_svc

    yield

    # 关闭：释放连接
    await milvus_svc.close()
    app.state.milvus = None


app = FastAPI(
    title="VDB Service",
    description="向量数据库统一服务，基于 Milvus Hybrid Search（embedding + BM25）",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)


if __name__ == "__main__":
    uvicorn.run(
        "vdb.main:app",
        host=config.host,
        port=config.port,
        reload=False,
    )
