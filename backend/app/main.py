from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api import auth, documents, review, compare, rules, terms, audit_basis, polish, qa, generate, convert, translation, knowledge, spell_check, whitelist, param_compare, manual_search, polish_rules, system, competitor
from app.database import create_tables
import threading
import os


def _is_production_like_env(value: str | None) -> bool:
    return str(value or "development").strip().lower() in {"prod", "production", "staging"}


def _ensure_bootstrap_admin(db, username: str, password: str):
    from app.crud.user import create_user_with_details, get_user, get_password_hash
    from app.schemas.user import UserCreateWithDetails

    admin_user = get_user(db, username)
    if not admin_user:
        create_user_with_details(db, UserCreateWithDetails(
            username=username,
            password=password,
            display_name="管理员",
            role="admin",
            status="active",
        ))
        print(f"[startup] 已创建管理员引导账号: {username}")
        return

    changed = False
    if admin_user.role != "admin":
        admin_user.role = "admin"
        changed = True
    if admin_user.status != "active":
        admin_user.status = "active"
        changed = True
    if not _is_production_like_env(os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or os.getenv("ENV")):
        admin_user.password_hash = get_password_hash(password)
        changed = True

    if changed:
        db.commit()
        db.refresh(admin_user)
        print(f"[startup] 已校正管理员引导账号: {username}")

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
app.include_router(competitor.router, prefix="/api/competitor", tags=["竞品分析"])
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

    def _warmup_audit_basis_search():
        try:
            from app.api.review import _build_ai_review_basis_sections, _load_review_spec_texts
            from app.services.audit_basis_search import get_audit_basis_search_service

            spec_texts = _load_review_spec_texts()
            basis_sections = _build_ai_review_basis_sections(spec_texts, "both")
            service = get_audit_basis_search_service()
            if service.warmup(basis_sections):
                print(f"[startup] 审核依据 ES 预热完成: {service.index_name}")
        except Exception as e:
            print(f"[startup] 审核依据 ES 预热失败: {e}")

    try:
        from app.utils.ai_client import ai_client
        threading.Thread(target=ai_client.warmup, name="ai-warmup", daemon=True).start()
    except Exception as e:
        print(f"[startup] AI 预热失败: {e}")
    threading.Thread(target=_warmup_audit_basis_search, name="audit-basis-es-warmup", daemon=True).start()
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
        bootstrap_username = (os.getenv("ADMIN_BOOTSTRAP_USERNAME") or "").strip()
        bootstrap_password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD") or ""
        runtime_env = os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or os.getenv("ENV")
        if (not bootstrap_username or not bootstrap_password) and not _is_production_like_env(runtime_env):
            bootstrap_username = bootstrap_username or "admin"
            bootstrap_password = bootstrap_password or "admin123"

        if not bootstrap_username or not bootstrap_password:
            print("[startup] 未配置管理员引导账号，跳过默认管理员初始化")
        else:
            db = SessionLocal()
            try:
                _ensure_bootstrap_admin(db, bootstrap_username, bootstrap_password)
            finally:
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
