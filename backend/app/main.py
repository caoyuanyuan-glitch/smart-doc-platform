from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import auth, documents, review, compare, rules, terms, audit_basis, polish, qa, generate, convert, knowledge
from app.database import create_tables

app = FastAPI(title="智能技术文档平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(documents.router, prefix="/api/documents", tags=["文档管理"])
app.include_router(review.router, prefix="/api/review", tags=["文档审核"])
app.include_router(compare.router, prefix="/api/compare", tags=["文档对比"])
app.include_router(rules.router, prefix="/api/rules", tags=["规则管理"])
app.include_router(terms.router, prefix="/api/terms", tags=["术语库"])
app.include_router(audit_basis.router, prefix="/api/audit_basis", tags=["审核依据"])
app.include_router(polish.router, prefix="/api/polish", tags=["智能润色"])
app.include_router(qa.router, prefix="/api/qa", tags=["智能问答"])
app.include_router(generate.router, prefix="/api/generate", tags=["内容生成"])
app.include_router(convert.router, prefix="/api/convert", tags=["格式转换"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库管理"])

@app.on_event("startup")
async def startup_event():
    create_tables()
    try:
        from seed.knowledge_seed import seed_knowledge_base
        seed_knowledge_base()
    except Exception as e:
        print(f"[startup] 知识库种子初始化失败: {e}")
    try:
        from seed.polished_seed import cleanup_orphan_polished_documents, seed_polished_documents
        cleanup_orphan_polished_documents()
        seed_polished_documents()
    except Exception as e:
        print(f"[startup] 已润色文档种子初始化失败: {e}")

@app.get("/")
async def root():
    return {"message": "智能技术文档平台 API"}
