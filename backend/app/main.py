from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import auth, documents, review, compare, rules, terms, audit_basis, polish, qa, generate, convert, translation, knowledge, spell_check, whitelist, param_compare, manual_search, polish_rules, system
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
app.include_router(param_compare.router, prefix="/api/compare/params", tags=["参数对比"])
app.include_router(rules.router, prefix="/api/rules", tags=["规则管理"])
app.include_router(terms.router, prefix="/api/terms", tags=["术语库"])
app.include_router(audit_basis.router, prefix="/api/audit_basis", tags=["审核依据"])
app.include_router(polish.router, prefix="/api/polish", tags=["智能润色"])
app.include_router(qa.router, prefix="/api/qa", tags=["智能问答"])
app.include_router(manual_search.router, prefix="/api/manual", tags=["说明书问答"])
app.include_router(generate.router, prefix="/api/generate", tags=["内容生成"])
app.include_router(convert.router, prefix="/api/convert", tags=["格式转换"])
app.include_router(translation.router, prefix="/api/translation", tags=["AI翻译"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库管理"])
app.include_router(spell_check.router, prefix="/api/spell-check", tags=["拼写检查"])
app.include_router(whitelist.router, prefix="/api/whitelist", tags=["白名单管理"])
app.include_router(polish_rules.router, tags=["润色规则管理"])
app.include_router(system.router, prefix="/api/system", tags=["系统状态"])

@app.on_event("startup")
async def startup_event():
    create_tables()
    try:
        from app.utils.ai_client import ai_client
        ai_client.warmup()
    except Exception as e:
        print(f"[startup] AI 预热失败: {e}")
    try:
        from app.database import SessionLocal
        from app.crud.convert_rule import seed_default_rules
        from app.crud.rule import seed_external_review_rules
        from app.crud.polish_learning_rule import seed_system_rules

        db = SessionLocal()
        try:
            seeded_count = seed_default_rules(db)
            if seeded_count:
                print(f"[startup] 已初始化 {seeded_count} 条默认转换规则")
            review_rule_count = seed_external_review_rules(db)
            if review_rule_count:
                print(f"[startup] 已初始化 {review_rule_count} 条外部评审规则")
            system_rule_count = seed_system_rules(db)
            if system_rule_count:
                print(f"[startup] 已初始化 {system_rule_count} 条润色系统规则")
        finally:
            db.close()
    except Exception as e:
        print(f"[startup] 转换规则种子初始化失败: {e}")
    try:
        from app.database import SessionLocal
        from app.crud.user import get_user, create_user_with_details, get_password_hash
        from app.schemas.user import UserCreateWithDetails
        db = SessionLocal()
        admin_user = get_user(db, "admin")
        if not admin_user:
            create_user_with_details(db, UserCreateWithDetails(
                username="admin", password="admin123",
                display_name="管理员", role="admin", status="active",
            ))
            print("[startup] 默认管理员已创建 (admin/admin123)")
        else:
            admin_user.password_hash = get_password_hash("admin123")
            admin_user.display_name = "管理员"
            admin_user.role = "admin"
            admin_user.status = "active"
            db.commit()
            print("[startup] 默认管理员已重置为 admin/admin123")
        db.close()
    except Exception as e:
        print(f"[startup] 管理员初始化失败: {e}")
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
