import re
import json
import os
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# 白名单存储文件路径
WHITELIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "whitelist.json")

# 确保数据目录存在
os.makedirs(os.path.dirname(WHITELIST_FILE), exist_ok=True)

# 默认白名单数据
DEFAULT_WHITELIST = {
    "products": [
        {"id": "p1", "word": "MGISP", "category": "产品名", "description": "MGI样本制备系统"},
        {"id": "p2", "word": "MGISP-960", "category": "产品名", "description": "高通量样本制备系统"},
        {"id": "p3", "word": "MGISP-100", "category": "产品名", "description": "中通量样本制备系统"},
        {"id": "p4", "word": "MGISP-Smart 8", "category": "产品名", "description": "智能样本制备系统"},
        {"id": "p5", "word": "DNBSEQ", "category": "产品名", "description": "DNBSEQ测序平台"},
        {"id": "p6", "word": "DNBSEQ-T20×2RS", "category": "产品名", "description": "超高通量测序仪"},
        {"id": "p7", "word": "MGICLab", "category": "产品名", "description": "MGI实验室自动化产品"},
        {"id": "p8", "word": "MGICLab-FZ90", "category": "产品名", "description": "分杯处理系统"},
        {"id": "p9", "word": "MGICLab-FZ150K", "category": "产品名", "description": "大规模分杯处理系统"},
        {"id": "p10", "word": "MGI", "category": "产品名", "description": "华大智造"}
    ],
    "brands": [
        {"id": "b1", "word": "Qubit", "category": "品牌名", "description": "Thermo Fisher品牌"},
        {"id": "b2", "word": "Eppendorf", "category": "品牌名", "description": "艾本德"},
        {"id": "b3", "word": "Hamilton", "category": "品牌名", "description": "汉密尔顿"},
        {"id": "b4", "word": "HamiLton", "category": "品牌名", "description": "汉密尔顿（变体）"},
        {"id": "b5", "word": "Thermo Fisher Scientific", "category": "品牌名", "description": "赛默飞世尔"},
        {"id": "b6", "word": "BMG LABTECH", "category": "品牌名", "description": "BMG实验室技术"},
        {"id": "b7", "word": "AXYGEN", "category": "品牌名", "description": "axygen"},
        {"id": "b8", "word": "Greiner Bio-One", "category": "品牌名", "description": "格瑞纳生物"},
        {"id": "b9", "word": "Fluostar Omega", "category": "品牌名", "description": "荧光读数仪"}
    ],
    "document_ids": [
        {"id": "d1", "word": "JB-A09-148", "category": "文档编号", "description": "标准文档编号格式"},
        {"id": "d2", "word": "V1.0", "category": "版本号", "description": "版本号格式"},
        {"id": "d3", "word": "V3.0", "category": "版本号", "description": "版本号格式"},
        {"id": "d4", "word": "940-002612-00", "category": "货号", "description": "标准货号格式"}
    ],
    "terms": [
        {"id": "t1", "word": "E. coli", "category": "科学术语", "description": "大肠杆菌"},
        {"id": "t2", "word": "DNA", "category": "生化术语", "description": "脱氧核糖核酸"},
        {"id": "t3", "word": "RNA", "category": "生化术语", "description": "核糖核酸"},
        {"id": "t4", "word": "PCR", "category": "生化术语", "description": "聚合酶链式反应"},
        {"id": "t5", "word": "ssCir", "category": "生化术语", "description": "单链环状DNA"},
        {"id": "t6", "word": "dsDNA", "category": "生化术语", "description": "双链DNA"},
        {"id": "t7", "word": "DNB", "category": "生化术语", "description": "DNA纳米球"},
        {"id": "t8", "word": "in situ", "category": "科学术语", "description": "原位"},
        {"id": "t9", "word": "in vitro", "category": "科学术语", "description": "体外"},
        {"id": "t10", "word": "in vivo", "category": "科学术语", "description": "体内"},
        {"id": "t11", "word": "et al.", "category": "科学术语", "description": "等"},
        {"id": "t12", "word": "DIPSEQ", "category": "生化术语", "description": "数字喷印测序"},
        {"id": "t13", "word": "OliGreen", "category": "生化术语", "description": "荧光染料"},
        {"id": "t14", "word": "MPC2000", "category": "设备型号", "description": "微孔板计数器"},
        {"id": "t15", "word": "ALPS 50V", "category": "设备型号", "description": "封板仪"}
    ],
    "domains": [
        {"id": "w1", "word": "mgi-tech.com", "category": "域名", "description": "MGI官网域名"},
        {"id": "w2", "word": "global-mgitech.com", "category": "域名", "description": "MGI国际官网域名"},
        {"id": "w3", "word": "MGI-service@mgi-tech.com", "category": "邮箱", "description": "MGI客服邮箱"}
    ]
}

def load_whitelist():
    """加载白名单数据"""
    if os.path.exists(WHITELIST_FILE):
        try:
            with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return DEFAULT_WHITELIST.copy()
    return DEFAULT_WHITELIST.copy()

def save_whitelist(data):
    """保存白名单数据"""
    with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_id():
    """生成唯一ID"""
    import time
    import random
    return f"{int(time.time() * 1000)}-{random.randint(1000, 9999)}"

class WhitelistItem(BaseModel):
    word: str
    category: str
    description: Optional[str] = ""

class WhitelistItemWithId(WhitelistItem):
    id: str

def get_all_items():
    """获取所有白名单条目"""
    data = load_whitelist()
    items = []
    for category, items_list in data.items():
        for item in items_list:
            items.append({**item, "category": item.get("category", category)})
    return items

def get_items_by_category():
    """按分类获取白名单"""
    return load_whitelist()

@router.get("/items", summary="获取所有白名单条目")
async def get_items():
    return {"items": get_all_items(), "categories": list(load_whitelist().keys())}

@router.get("/categories", summary="获取白名单分类")
async def get_categories():
    data = load_whitelist()
    category_names = {
        "products": "产品名",
        "brands": "品牌名",
        "document_ids": "文档编号",
        "terms": "专业术语",
        "domains": "域名邮箱"
    }
    return [
        {"key": k, "name": category_names.get(k, k), "count": len(v)}
        for k, v in data.items()
    ]

@router.post("/items", summary="添加白名单条目")
async def add_item(item: WhitelistItem):
    data = load_whitelist()
    
    # 确定添加到哪个分类
    category_map = {
        "产品名": "products",
        "品牌名": "brands",
        "文档编号": "document_ids",
        "版本号": "document_ids",
        "货号": "document_ids",
        "科学术语": "terms",
        "生化术语": "terms",
        "设备型号": "terms",
        "域名": "domains",
        "邮箱": "domains"
    }
    
    category_key = category_map.get(item.category, "terms")
    
    new_item = {
        "id": generate_id(),
        "word": item.word,
        "category": item.category,
        "description": item.description or ""
    }
    
    data[category_key].append(new_item)
    save_whitelist(data)
    
    return {"message": "添加成功", "item": new_item}

@router.put("/items/{item_id}", summary="更新白名单条目")
async def update_item(item_id: str, item: WhitelistItem):
    data = load_whitelist()
    
    for category_key, items in data.items():
        for i, existing_item in enumerate(items):
            if existing_item.get("id") == item_id:
                items[i] = {
                    "id": item_id,
                    "word": item.word,
                    "category": item.category,
                    "description": item.description or ""
                }
                save_whitelist(data)
                return {"message": "更新成功", "item": items[i]}
    
    raise HTTPException(status_code=404, detail="条目不存在")

@router.delete("/items/{item_id}", summary="删除白名单条目")
async def delete_item(item_id: str):
    data = load_whitelist()
    
    for category_key, items in data.items():
        for i, item in enumerate(items):
            if item.get("id") == item_id:
                deleted = items.pop(i)
                save_whitelist(data)
                return {"message": "删除成功", "item": deleted}
    
    raise HTTPException(status_code=404, detail="条目不存在")

@router.post("/items/batch-delete", summary="批量删除白名单条目")
async def batch_delete(item_ids: List[str]):
    data = load_whitelist()
    deleted = []
    
    for category_key, items in data.items():
        items[:] = [item for item in items if item.get("id") not in item_ids]
        for item_id in item_ids:
            for item in items:
                if item.get("id") == item_id and item not in deleted:
                    deleted.append(item)
    
    save_whitelist(data)
    return {"message": f"成功删除 {len(deleted)} 条", "deleted_count": len(deleted)}

@router.post("/import", summary="导入白名单")
async def import_whitelist(items: List[WhitelistItem]):
    data = load_whitelist()
    added = []
    
    category_map = {
        "产品名": "products",
        "品牌名": "brands",
        "文档编号": "document_ids",
        "版本号": "document_ids",
        "货号": "document_ids",
        "科学术语": "terms",
        "生化术语": "terms",
        "设备型号": "terms",
        "域名": "domains",
        "邮箱": "domains"
    }
    
    for item in items:
        category_key = category_map.get(item.category, "terms")
        
        # 检查是否已存在
        exists = False
        for existing in data[category_key]:
            if existing.get("word", "").lower() == item.word.lower():
                exists = True
                break
        
        if not exists:
            new_item = {
                "id": generate_id(),
                "word": item.word,
                "category": item.category,
                "description": item.description or ""
            }
            data[category_key].append(new_item)
            added.append(new_item)
    
    save_whitelist(data)
    return {"message": f"成功导入 {len(added)} 条", "added_count": len(added), "skipped": len(items) - len(added)}

@router.get("/export", summary="导出白名单")
async def export_whitelist():
    items = get_all_items()
    return {"items": items, "total": len(items)}

@router.post("/reset", summary="重置白名单为默认")
async def reset_whitelist():
    save_whitelist(DEFAULT_WHITELIST.copy())
    return {"message": "白名单已重置为默认"}
