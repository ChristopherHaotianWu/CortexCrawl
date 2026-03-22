#!/usr/bin/env python3
"""
DEPLOYMENT.md → 飞书云文档 同步脚本

将项目根目录的 DEPLOYMENT.md 转换为飞书文档 block 并同步到云文档。
首次运行自动创建文档，后续运行清空并重写内容。

API 参考: https://open.feishu.cn/document/server-docs/docs/docs-overview
- 创建文档: POST /docx/v1/documents
- 列出 block: GET /docx/v1/documents/:id/blocks (page_size 上限 500)
- 批量新增子 block: POST /docx/v1/documents/:id/blocks/:block_id/children/batch_create
- 批量删除子 block: DELETE /docx/v1/documents/:id/blocks/:block_id/children/batch_delete
- Token: POST /auth/v3/tenant_access_token/internal (有效期 2 小时)
"""
import os
import re
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import requests
from dotenv import load_dotenv, set_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# ─── Feishu block type constants ───────────────────────────────────────────
BLOCK_PAGE = 1
BLOCK_TEXT = 2
BLOCK_HEADING1 = 3
BLOCK_HEADING2 = 4
BLOCK_HEADING3 = 5
BLOCK_HEADING4 = 6
BLOCK_HEADING5 = 7
BLOCK_HEADING6 = 8
BLOCK_HEADING7 = 9
BLOCK_HEADING8 = 10
BLOCK_HEADING9 = 11
BLOCK_BULLET = 12
BLOCK_ORDERED = 13
BLOCK_CODE = 14
BLOCK_DIVIDER = 15

# Feishu code language enum (subset)
_CODE_LANG = {
    "bash": 7, "sh": 7, "shell": 7,
    "python": 49, "py": 49,
    "json": 34, "yaml": 82, "yml": 82,
    "javascript": 33, "js": 33,
    "sql": 59, "cron": 7, "env": 7,
    "": 45,  # plaintext
}


# ═══════════════════════════════════════════════════════════════════════════
# Feishu Document API Client
# ═══════════════════════════════════════════════════════════════════════════

class FeishuDocClient:
    """飞书云文档 API 客户端"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token: Optional[str] = None
        self._token_expire_time: Optional[datetime] = None
        self._session = requests.Session()

    def _request(self, method: str, url: str, max_retries: int = 3, **kwargs) -> requests.Response:
        for attempt in range(max_retries):
            try:
                resp = self._session.request(method, url, timeout=30, **kwargs)
                if resp.status_code in _RETRYABLE_STATUS and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"HTTP {resp.status_code}, retry in {wait}s ({attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue
                if resp.status_code >= 400:
                    logger.error(f"HTTP {resp.status_code}: {resp.text[:500]}")
                resp.raise_for_status()
                return resp
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def _get_token(self) -> str:
        if self._access_token and self._token_expire_time and datetime.now() < self._token_expire_time:
            return self._access_token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        resp = self._request("POST", url, headers={"Content-Type": "application/json"}, json={
            "app_id": self.app_id, "app_secret": self.app_secret
        })
        result = resp.json()
        if result.get("code") != 0:
            raise Exception(f"获取 token 失败: {result}")

        self._access_token = result["tenant_access_token"]
        self._token_expire_time = datetime.now() + timedelta(seconds=result.get("expire", 7200) - 300)
        return self._access_token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json; charset=utf-8"}

    # ── Document CRUD ──────────────────────────────────────────────────────

    def create_document(self, title: str, folder_token: str = "") -> str:
        """创建云文档，返回 document_id"""
        url = f"{self.BASE_URL}/docx/v1/documents"
        body: Dict[str, Any] = {"title": title}
        if folder_token:
            body["folder_token"] = folder_token
        resp = self._request("POST", url, headers=self._headers(), json=body)
        result = resp.json()
        if result.get("code") != 0:
            raise Exception(f"创建文档失败: {result}")
        doc_id = result["data"]["document"]["document_id"]
        logger.info(f"文档已创建: https://open.feishu.cn/docx/{doc_id}")
        return doc_id

    def get_document(self, doc_id: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/docx/v1/documents/{doc_id}"
        resp = self._request("GET", url, headers=self._headers())
        result = resp.json()
        if result.get("code") != 0:
            raise Exception(f"获取文档失败: {result}")
        return result["data"]["document"]

    # ── Wiki operations ─────────────────────────────────────────────────────

    def get_wiki_node(self, node_token: str) -> Dict[str, Any]:
        """通过 wiki node_token 获取节点信息，返回 obj_token (即 document_id)"""
        url = f"{self.BASE_URL}/wiki/v2/spaces/get_node"
        resp = self._request("GET", url, headers=self._headers(), params={"token": node_token})
        result = resp.json()
        if result.get("code") != 0:
            raise Exception(f"获取 wiki 节点失败: {result}")
        node = result["data"]["node"]
        logger.info(f"Wiki 节点: {node.get('title', '')}, obj_type={node.get('obj_type')}, obj_token={node.get('obj_token')}")
        return node

    def update_page_title(self, doc_id: str, title: str) -> None:
        """更新文档标题 (修改 page block 的 text_elements)"""
        url = f"{self.BASE_URL}/docx/v1/documents/{doc_id}/blocks/{doc_id}"
        body = {
            "update_text_elements": {
                "elements": [{"text_run": {"content": title}}],
                "style": {}
            }
        }
        result = self._request_safe("PATCH", url, headers=self._headers(), json=body)
        if result.get("code") != 0:
            logger.warning(f"更新标题失败 (可忽略): {result.get('msg', '')[:80]}")
        else:
            logger.info(f"文档标题已更新: {title}")

    # ── Block operations ───────────────────────────────────────────────────

    def list_blocks(self, doc_id: str) -> List[Dict[str, Any]]:
        """列出文档所有 block (自动分页)"""
        url = f"{self.BASE_URL}/docx/v1/documents/{doc_id}/blocks"
        blocks = []
        page_token = None
        while True:
            params: Dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            resp = self._request("GET", url, headers=self._headers(), params=params)
            result = resp.json()
            if result.get("code") != 0:
                raise Exception(f"列出 block 失败: {result}")
            blocks.extend(result.get("data", {}).get("items", []))
            if not result.get("data", {}).get("has_more"):
                break
            page_token = result["data"]["page_token"]
        return blocks

    def delete_children(self, doc_id: str, block_id: str, child_count: int) -> None:
        """删除指定 block 下的所有子 block

        API: DELETE /docx/v1/documents/:document_id/blocks/:block_id/children/batch_delete
        每次删除第 0 个，重复 child_count 次（删除后索引自动前移）
        """
        if child_count <= 0:
            return
        url = f"{self.BASE_URL}/docx/v1/documents/{doc_id}/blocks/{block_id}/children/batch_delete"
        # 每次删第 0 个到第 min(50, remaining) 个，批量删除
        remaining = child_count
        while remaining > 0:
            batch = min(50, remaining)
            body = {"start_index": 0, "end_index": batch}
            resp = self._request("DELETE", url, headers=self._headers(), json=body)
            result = resp.json()
            if result.get("code") != 0:
                raise Exception(f"删除 block 失败: {result}")
            remaining -= batch
            if remaining > 0:
                time.sleep(0.3)
        logger.info(f"已删除 {child_count} 个 block")

    def create_children(self, doc_id: str, block_id: str, children: List[Dict[str, Any]],
                         index: int = -1) -> None:
        """创建子 block，批量发送，失败时逐个重试跳过坏 block

        API: POST /docx/v1/documents/:document_id/blocks/:block_id/children
        """
        url = f"{self.BASE_URL}/docx/v1/documents/{doc_id}/blocks/{block_id}/children"
        batch_size = 50
        current_index = 0 if index == -1 else index
        created = 0
        skipped = 0

        for i in range(0, len(children), batch_size):
            batch = children[i:i + batch_size]
            body: Dict[str, Any] = {"children": batch, "index": current_index}
            result = self._request_safe("POST", url, headers=self._headers(), json=body)

            if result.get("code") == 0:
                current_index += len(batch)
                created += len(batch)
            else:
                # 批量失败，逐个发送找出并跳过坏 block
                logger.warning(f"批量创建失败 (code={result.get('code')}), 逐个重试...")
                for j, child in enumerate(batch):
                    single_body = {"children": [child], "index": current_index}
                    single_result = self._request_safe("POST", url, headers=self._headers(), json=single_body)
                    if single_result.get("code") == 0:
                        current_index += 1
                        created += 1
                    else:
                        skipped += 1
                        logger.warning(f"跳过 block {i + j} (type={child.get('block_type')}): {single_result.get('msg', '')[:80]}")
                    time.sleep(0.3)  # 逐个发送时加延迟避免限流

            if i + batch_size < len(children):
                time.sleep(0.5)

        logger.info(f"已创建 {created} 个 block, 跳过 {skipped} 个")

    def _request_safe(self, method: str, url: str, max_retries: int = 3, **kwargs) -> Dict[str, Any]:
        """HTTP 请求，返回 JSON dict，不抛异常，自动重试限流"""
        for attempt in range(max_retries):
            try:
                resp = self._session.request(method, url, timeout=30, **kwargs)
                if resp.status_code == 429:
                    wait = 2 ** attempt + 1
                    logger.warning(f"限流 429, {wait}s 后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue
                result = resp.json()
                # 飞书有时返回频率限制错误码
                if result.get("code") == 99991400:
                    wait = 2 ** attempt + 1
                    logger.warning(f"频率限制, {wait}s 后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue
                return result
            except requests.exceptions.JSONDecodeError:
                # 空响应，通常是限流
                if attempt < max_retries - 1:
                    wait = 2 ** attempt + 1
                    logger.warning(f"空响应 (限流), {wait}s 后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(wait)
                    continue
                return {"code": -1, "msg": "empty response after retries"}
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return {"code": -1, "msg": str(e)}
        return {"code": -1, "msg": "max retries exceeded"}


# ═══════════════════════════════════════════════════════════════════════════
# Markdown → Feishu Blocks Converter
# ═══════════════════════════════════════════════════════════════════════════

def _text_run(content: str, bold: bool = False, italic: bool = False,
              inline_code: bool = False, link: str = "") -> Dict[str, Any]:
    """构造一个 text_run 元素 (始终包含 text_element_style)"""
    style: Dict[str, Any] = {
        "bold": bold,
        "italic": italic,
        "inline_code": inline_code,
        "strikethrough": False,
        "underline": False,
    }
    # 飞书只支持完整 URL，不支持锚点链接 (#...)
    if link and not link.startswith("#"):
        style["link"] = {"url": link}
    return {"text_run": {"content": content, "text_element_style": style}}


def _parse_inline(text: str) -> List[Dict[str, Any]]:
    """解析行内 Markdown 格式，返回 text_run 元素列表"""
    elements: List[Dict[str, Any]] = []
    # Pattern: **bold**, *italic*, `code`, [text](url)
    pattern = r'(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`|\[(.+?)\]\((.+?)\))'

    last_end = 0
    for m in re.finditer(pattern, text):
        # 匹配前的普通文本
        if m.start() > last_end:
            plain = text[last_end:m.start()]
            if plain:
                elements.append(_text_run(plain))

        if m.group(2):  # **bold**
            elements.append(_text_run(m.group(2), bold=True))
        elif m.group(3):  # *italic*
            elements.append(_text_run(m.group(3), italic=True))
        elif m.group(4):  # `code`
            elements.append(_text_run(m.group(4), inline_code=True))
        elif m.group(5):  # [text](url)
            elements.append(_text_run(m.group(5), link=m.group(6)))

        last_end = m.end()

    # 剩余文本
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            elements.append(_text_run(remaining))

    if not elements:
        elements.append(_text_run(text))

    return elements


def _make_block(block_type: int, elements: List[Dict[str, Any]], **extra) -> Dict[str, Any]:
    """构造一个飞书 block (包含必需的 style 字段)"""
    type_name_map = {
        BLOCK_TEXT: "text", BLOCK_HEADING1: "heading1", BLOCK_HEADING2: "heading2",
        BLOCK_HEADING3: "heading3", BLOCK_HEADING4: "heading4", BLOCK_HEADING5: "heading5",
        BLOCK_HEADING6: "heading6", BLOCK_HEADING7: "heading7", BLOCK_HEADING8: "heading8",
        BLOCK_HEADING9: "heading9",
        BLOCK_BULLET: "bullet", BLOCK_ORDERED: "ordered",
    }
    name = type_name_map.get(block_type)
    if name:
        body: Dict[str, Any] = {"elements": elements, "style": {}}
        body.update(extra)
        return {"block_type": block_type, name: body}
    raise ValueError(f"Unsupported block type: {block_type}")


def _make_code_block(code: str, language: str = "") -> Dict[str, Any]:
    """构造代码块"""
    lang_id = _CODE_LANG.get(language.lower(), 45)
    return {
        "block_type": BLOCK_CODE,
        "code": {
            "elements": [{"text_run": {"content": code, "text_element_style": {}}}],
            "style": {"language": lang_id}
        }
    }


def _make_divider() -> Dict[str, Any]:
    """分割线 — 飞书 API 不支持直接创建 divider block，用空行代替"""
    return _make_block(BLOCK_TEXT, [_text_run(" ")])


def markdown_to_blocks(md_content: str) -> List[Dict[str, Any]]:
    """将 Markdown 内容转换为飞书 block 列表"""
    blocks: List[Dict[str, Any]] = []
    lines = md_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── 空行跳过 ──
        if not line.strip():
            i += 1
            continue

        # ── 分割线 ──
        if re.match(r'^-{3,}$', line.strip()):
            blocks.append(_make_divider())
            i += 1
            continue

        # ── 代码块 ──
        fence_match = re.match(r'^```(\w*)', line)
        if fence_match:
            lang = fence_match.group(1)
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            blocks.append(_make_code_block("\n".join(code_lines), lang))
            continue

        # ── 标题 ──
        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            block_type = BLOCK_HEADING1 + level - 1  # h1=3, h2=4, ...
            blocks.append(_make_block(block_type, _parse_inline(text)))
            i += 1
            continue

        # ── 表格 → 代码块 ──
        if line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append(_make_code_block("\n".join(table_lines)))
            continue

        # ── 无序列表 ──
        bullet_match = re.match(r'^(\s*)[-*]\s+(.*)', line)
        if bullet_match:
            text = bullet_match.group(2).strip()
            blocks.append(_make_block(BLOCK_BULLET, _parse_inline(text)))
            i += 1
            continue

        # ── 有序列表 ──
        ordered_match = re.match(r'^(\s*)\d+\.\s+(.*)', line)
        if ordered_match:
            text = ordered_match.group(2).strip()
            blocks.append(_make_block(BLOCK_ORDERED, _parse_inline(text)))
            i += 1
            continue

        # ── 引用 ──
        quote_match = re.match(r'^>\s*(.*)', line)
        if quote_match:
            text = quote_match.group(1).strip()
            if text:
                blocks.append(_make_block(BLOCK_TEXT, _parse_inline(text)))
            i += 1
            continue

        # ── 普通段落 ──
        blocks.append(_make_block(BLOCK_TEXT, _parse_inline(line.strip())))
        i += 1

    return blocks


# ═══════════════════════════════════════════════════════════════════════════
# Sync Orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def _parse_wiki_url(url: str) -> Optional[str]:
    """从飞书 wiki URL 中提取 node_token"""
    m = re.search(r'/wiki/([A-Za-z0-9]+)', url)
    return m.group(1) if m else None


def _parse_docx_url(url: str) -> Optional[str]:
    """从飞书 docx URL 中提取 document_id"""
    m = re.search(r'/docx/([A-Za-z0-9]+)', url)
    return m.group(1) if m else None


def main():
    load_dotenv(DOTENV_PATH)

    app_id = os.getenv("FEISHU_DOC_APP_ID", "")
    app_secret = os.getenv("FEISHU_DOC_APP_SECRET", "")
    doc_id = os.getenv("FEISHU_DOC_ID", "")
    wiki_url = os.getenv("FEISHU_WIKI_URL", "")

    if not app_id or not app_secret:
        logger.error("请在 .env 中配置 FEISHU_DOC_APP_ID 和 FEISHU_DOC_APP_SECRET")
        sys.exit(1)

    # 读取 DEPLOYMENT.md
    md_path = PROJECT_ROOT / "DEPLOYMENT.md"
    if not md_path.exists():
        logger.error(f"文件不存在: {md_path}")
        sys.exit(1)

    md_content = md_path.read_text(encoding="utf-8")
    blocks = markdown_to_blocks(md_content)
    logger.info(f"Markdown 转换完成: {len(blocks)} 个 block")

    client = FeishuDocClient(app_id, app_secret)

    # 解析文档 ID：支持 wiki URL、docx URL、或直接 doc_id
    if not doc_id and wiki_url:
        node_token = _parse_wiki_url(wiki_url)
        if node_token:
            logger.info(f"从 wiki URL 解析 node_token: {node_token}")
            node = client.get_wiki_node(node_token)
            doc_id = node["obj_token"]
            set_key(str(DOTENV_PATH), "FEISHU_DOC_ID", doc_id)
            logger.info(f"Wiki document_id 已写入 .env: {doc_id}")
        else:
            # 尝试作为 docx URL 解析
            doc_id = _parse_docx_url(wiki_url)
            if doc_id:
                set_key(str(DOTENV_PATH), "FEISHU_DOC_ID", doc_id)

    if not doc_id:
        logger.info("FEISHU_DOC_ID 和 FEISHU_WIKI_URL 均为空，创建新文档...")
        doc_id = client.create_document("CortexCrawl — 完整部署手册")
        set_key(str(DOTENV_PATH), "FEISHU_DOC_ID", doc_id)
        logger.info(f"文档 ID 已写入 .env: {doc_id}")

    # 设置文档标题
    client.update_page_title(doc_id, "CortexCrawl — 完整部署手册")

    # 清空现有内容
    existing_blocks = client.list_blocks(doc_id)
    # 第一个 block 是 page 根节点，其余是实际内容
    child_count = len(existing_blocks) - 1 if existing_blocks else 0
    if child_count > 0:
        logger.info(f"清空文档现有 {child_count} 个 block...")
        client.delete_children(doc_id, doc_id, child_count)

    # 写入新内容
    client.create_children(doc_id, doc_id, blocks)

    logger.info(f"同步完成! wiki: {wiki_url or 'N/A'}, doc_id: {doc_id}")
    print(f"OK: {len(blocks)} blocks synced to doc_id={doc_id}")


if __name__ == "__main__":
    main()
